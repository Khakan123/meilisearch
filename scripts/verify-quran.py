"""Isolated HTTP regression + benchmark; never connects to an existing server."""
import argparse
import json
import math
import os
from pathlib import Path
import socket
import statistics
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

QUERIES = [("ٱلصَّلَوٰة", [1]), ("كتاب", [2, 10, 11]), ("کتب", [3]),
           ("رحمة", [4]), ("رحمہ", [5]), ("ولیی", [6]), ("الله", [7]),
           ("ابراہیم", [8]), ("الرحمن", [9]), ("بہ", [12]), ("علی", [13]), ("شیئ", [14])]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("--runs", type=int, default=10)
    args = parser.parse_args()
    binary = args.binary.resolve(strict=True)
    if args.runs < 1:
        parser.error("--runs must be positive")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    def api(path, body=None, method=None, expected=200):
        req = urllib.request.Request(url+path, data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type":"application/json"}, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                code, data = response.status, response.read()
        except urllib.error.HTTPError as error:
            code, data = error.code, error.read()
        assert code == expected, (path,code,data)
        return json.loads(data) if data else None
    def task(response):
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            result=api(f"/tasks/{response['taskUid']}")
            if result['status']=='succeeded': return
            assert result['status'] not in ('failed','canceled'), result
            time.sleep(.05)
        raise TimeoutError(response)
    with tempfile.TemporaryDirectory(prefix="jamia-quran-") as directory:
        env={k:v for k,v in os.environ.items() if not k.startswith('MEILI_')}
        log_path=Path(directory)/'server.log'
        with log_path.open('wb') as log:
            process=None
            def start():
                proc=subprocess.Popen([str(binary),'--db-path',str(Path(directory)/'data.ms'),
                    '--http-addr',f'127.0.0.1:{port}','--no-analytics'],cwd=directory,env=env,
                    stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                deadline=time.monotonic()+60
                while time.monotonic()<deadline:
                    if proc.poll() is not None:
                        raise RuntimeError(log_path.read_text(errors='replace'))
                    try:
                        api('/health');return proc
                    except (urllib.error.URLError,TimeoutError):time.sleep(.1)
                proc.terminate();proc.wait(timeout=15)
                raise TimeoutError('server startup')
            try:
                process=start()
                task(api('/indexes',{'uid':'quran_fixture','primaryKey':'id'},expected=202))
                settings={'searchableAttributes':['text'],
                    'localizedAttributes':[{'attributePatterns':['text'],'locales':['qur']}],
                    'typoTolerance':{'enabled':False},'prefixSearch':'disabled'}
                task(api('/indexes/quran_fixture/settings',settings,method='PATCH',expected=202))
                fixtures=json.loads(Path(__file__).with_name('quran-fixtures.json').read_text(encoding='utf-8'))
                begin=time.perf_counter()
                task(api('/indexes/quran_fixture/documents',fixtures,expected=202))
                indexing_ms=(time.perf_counter()-begin)*1000
                def search(query):
                    return api('/indexes/quran_fixture/search',{'q':query,'locales':['qur'],
                        'attributesToHighlight':['text'],'showMatchesPosition':True,'limit':100})
                for query,ids in QUERIES:
                    result=search(query)
                    assert sorted(h['id'] for h in result['hits'])==ids,(query,result)
                    for hit in result['hits']:
                        raw=next(d['text'] for d in fixtures if d['id']==hit['id'])
                        assert hit['text']==raw
                        assert hit['_formatted']['text'].replace('<em>','').replace('</em>','')==raw
                        for span in hit['_matchesPosition']['text']:
                            raw.encode()[:span['start']].decode()
                            raw.encode()[span['start']:span['start']+span['length']].decode()
                api('/indexes/quran_fixture/search',{'q':'کتاب','locales':['qur-loose']},expected=400)
                # Cropping uses original text and must remain valid Unicode.
                api('/indexes/quran_fixture/search',{'q':'ولیی','locales':['qur'],
                    'attributesToCrop':['text'],'cropLength':1,'attributesToHighlight':['text']})
                timings=[]; server_times=[]
                for _ in range(args.runs):
                    for query,_ in QUERIES:
                        begin=time.perf_counter(); result=search(query)
                        timings.append((time.perf_counter()-begin)*1000)
                        server_times.append(result['processingTimeMs'])
                task(api('/indexes/quran_fixture/documents',[{'id':2,'text':'الرَّحْمَة'}],method='PUT',expected=202))
                assert [h['id'] for h in search('الرحمۃ')['hits']]==[2]
                process.terminate();process.wait(timeout=15);process=None
                process=start()
                assert api('/indexes/quran_fixture/settings')['localizedAttributes']==settings['localizedAttributes']
                assert [h['id'] for h in search('الرحمۃ')['hits']]==[2]
                assert [h['id'] for h in search('ولیی')['hits']]==[6]
                print(json.dumps({'status':'passed','version':api('/version'),'documents':len(fixtures),
                    'requests':len(timings),'indexing_ms':round(indexing_ms,2),
                    'median_ms':round(statistics.median(timings),2),
                    'p95_ms':round(sorted(timings)[math.ceil(.95*len(timings))-1],2),
                    'server_median_ms':statistics.median(server_times),'restart_verified':True},indent=2))
            except Exception:
                log.flush()
                print(log_path.read_text(errors='replace')[-8000:])
                raise
            finally:
                if process is not None:
                    process.terminate()
                    try:process.wait(timeout=15)
                    except subprocess.TimeoutExpired:process.kill();process.wait()
if __name__=='__main__':main()
