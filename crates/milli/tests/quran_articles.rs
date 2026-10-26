use bumpalo::Bump;
use charabia::Language;
use heed::EnvOpenOptions;
use http_client::policy::IpPolicy;
use milli::progress::Progress;
use milli::update::new::indexer;
use milli::update::{IndexerConfig, MissingDocumentPolicy, Settings};
use milli::{Criterion, Index, MustStopProcessing, QuranArticleForm};
use std::io::Write;

fn pair() -> Vec<QuranArticleForm> {
    vec![QuranArticleForm {
        with_article: "الكتاب".into(), without_article: "كتاب".into()
    }]
}

#[test]
fn quran_articles_bidirectional_ranking_and_query_only_settings() {
    let dir = tempfile::tempdir().unwrap();
    let mut options = EnvOpenOptions::new().read_txn_without_tls();
    options.map_size(64 * 1024 * 1024);
    let index =
        Index::new(options, dir.path(), milli::CreateOrOpen::create_without_shards()).unwrap();
    let config = IndexerConfig::default();
    let stop = MustStopProcessing::default();
    let progress = Progress::quiet();
    let ip = IpPolicy::danger_always_allow();
    let mut txn = index.write_txn().unwrap();
    let mut settings = Settings::new(&mut txn, &index, &config);
    settings.set_primary_key("id".into());
    settings.set_searchable_fields(vec!["text".into()]);
    settings.set_localized_attributes_rules(vec![milli::LocalizedAttributesRule::new(
        vec!["text".into()],
        vec![Language::Qur],
    )]);
    settings.set_authorize_typos(false);
    settings.set_prefix_search(milli::index::PrefixSearch::Disabled);
    settings.set_criteria(vec![
        Criterion::Words,
        Criterion::Typo,
        Criterion::Exactness,
        Criterion::Proximity,
    ]);
    settings.execute(&stop, &progress, &ip, Default::default()).unwrap();
    txn.commit().unwrap();

    let rtxn = index.read_txn().unwrap();
    let mut wtxn = index.write_txn().unwrap();
    let old_fields = index.fields_ids_map(&rtxn).unwrap();
    let mut new_fields = old_fields.clone();
    let data = r#"{"id":"bare","text":"كتاب"}
{"id":"article","text":"الكتاب"}
{"id":"attached","text":"والكتاب"}
"#;
    let mut file = tempfile::tempfile().unwrap();
    file.write_all(data.as_bytes()).unwrap();
    file.sync_all().unwrap();
    let payload = unsafe { memmap2::Mmap::map(&file).unwrap() };
    let mut operations = indexer::IndexOperations::new();
    operations.replace_documents(&payload, MissingDocumentPolicy::default()).unwrap();
    let alloc = Bump::new();
    let (changes, stats, key) = operations
        .into_changes(&alloc, &index, &rtxn, None, &mut new_fields, &stop, Progress::quiet(), None)
        .unwrap();
    assert!(stats.into_iter().all(|s| s.error.is_none()));
    indexer::index(
        &mut wtxn,
        &index,
        &milli::ThreadPoolNoAbortBuilder::new().build().unwrap(),
        config.grenad_parameters(),
        &old_fields,
        new_fields,
        key,
        &changes,
        Default::default(),
        &stop,
        &progress,
        &ip,
        &Default::default(),
    )
    .unwrap();
    wtxn.commit().unwrap();
    drop(rtxn);

    let search = |query: &str, locale: Language| {
        let txn = index.read_txn().unwrap();
        let fields = index.fields_ids_map(&txn).unwrap();
        let mut s = index.search(&txn, "test", &fields, time::OffsetDateTime::now_utc(), &progress);
        s.query(query).locales(vec![locale]);
        let result = s.execute().unwrap();
        result
            .documents_ids
            .into_iter()
            .map(|id| {
                let (_, doc) = index.documents(&txn, [id]).unwrap().pop().unwrap();
                let id_field = fields.id("id").unwrap();
                serde_json::from_slice::<String>(doc.get(id_field).unwrap()).unwrap()
            })
            .collect::<Vec<_>>()
    };
    assert_eq!(search("كتاب", Language::Qur), ["bare"]);
    let mut txn = index.write_txn().unwrap();
    let mut settings = Settings::new(&mut txn, &index, &config);
    settings.set_quran_article_forms(pair());
    assert!(
        settings.execute(&stop, &progress, &ip, Default::default()).unwrap().is_none(),
        "article settings must not reindex existing documents"
    );
    txn.commit().unwrap();
    let old_snapshot = index.read_txn().unwrap();
    assert_eq!(index.quran_article_alternatives(&old_snapshot, "کتاب").unwrap(), ["الکتاب"]);
    assert_eq!(search("كتاب", Language::Qur), ["bare", "article"]);
    assert_eq!(search("الكتاب", Language::Qur), ["article", "bare"]);
    assert_eq!(search("والكتاب", Language::Qur), ["attached"]);
    let mut txn = index.write_txn().unwrap();
    let mut settings = Settings::new(&mut txn, &index, &config);
    settings.reset_quran_article_forms();
    assert!(
        settings.execute(&stop, &progress, &ip, Default::default()).unwrap().is_none(),
        "article reset must not reindex existing documents"
    );
    txn.commit().unwrap();
    assert_eq!(search("كتاب", Language::Qur), ["bare"]);
    let new_snapshot = index.read_txn().unwrap();
    assert!(index.quran_article_alternatives(&new_snapshot, "کتاب").unwrap().is_empty());
    assert_eq!(index.quran_article_alternatives(&old_snapshot, "کتاب").unwrap(), ["الکتاب"]);
}

#[test]
fn quran_articles_reject_unindexable_length() {
    let word = "ک".repeat(milli::MAX_WORD_LENGTH);
    assert!(milli::validate_quran_article_forms(vec![QuranArticleForm {
        with_article: format!("ال{word}"),
        without_article: word,
    }])
    .is_err());
}
