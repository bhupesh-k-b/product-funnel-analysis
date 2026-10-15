"""Download public source files and verify their exact SHA-256 checksums."""
from pathlib import Path
import hashlib
import json
import shutil
import ssl
import urllib.request
import zipfile
import certifi

ROOT=Path(__file__).resolve().parents[1]

def checksum(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def main():
    metadata=json.loads((ROOT/'data/sources.json').read_text())
    raw=ROOT/'data/raw';raw.mkdir(parents=True,exist_ok=True)
    for source in metadata['files']:
        path=raw/source['filename']
        if path.exists() and checksum(path)==source['sha256']:
            print(f'Verified {path.name}');continue
        temp=path.with_suffix('.download')
        extracted=path.with_suffix('.verified')
        try:
            req=urllib.request.Request(source['download_url'],headers={'User-Agent':'portfolio-data-downloader/1.0'})
            with urllib.request.urlopen(req,context=ssl.create_default_context(cafile=certifi.where()),timeout=120) as response,temp.open('wb') as output:
                shutil.copyfileobj(response,output)
            if zipfile.is_zipfile(temp):
                with zipfile.ZipFile(temp) as archive,archive.open(source['filename']) as data,extracted.open('wb') as output:
                    shutil.copyfileobj(data,output)
            else:temp.replace(extracted)
            if checksum(extracted)!=source['sha256']:
                raise ValueError(f"Checksum changed for {path.name}; inspect the source version before updating data/sources.json")
            extracted.replace(path)
            print(f'Downloaded and verified {path.name}')
        finally:
            temp.unlink(missing_ok=True);extracted.unlink(missing_ok=True)

if __name__=='__main__':main()
