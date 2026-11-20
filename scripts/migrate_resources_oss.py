#!/usr/bin/env python3
"""Create private, checksum-labelled OSS archives; never deletes source files."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]
RESOURCE_PATHS = [
    'outputs', 'deps', 'local/frog', 'local/frog-omp', 'local/frog-llvm-omp',
    'local/secrets', 'local/budgets', 'draft_5cae28b8_folder', 'draft_70f5ede3_folder',
    'SUBTLEX-NL with pos and Zipf.xlsx', '各级词汇lemma表.xlsx',
    'word_forms_levels.xlsx', '荷兰语词汇分级报告.xlsx',
]


def digest_file(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(4*1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def resources(root=ROOT):
    entries=[]
    for name in RESOURCE_PATHS:
        start=root/name
        if not start.exists():
            continue
        paths=[start]
        if start.is_dir():
            for base, dirs, files in os.walk(start,followlinks=False):
                paths.extend(Path(base)/n for n in dirs+files)
        for path in paths:
            if path.name=='.DS_Store':
                continue
            relative=path.relative_to(root).as_posix()
            if path.is_symlink():
                entries.append({'path':relative,'type':'symlink','target':os.readlink(path)})
            elif path.is_file():
                st=path.stat()
                entries.append({'path':relative,'type':'file','size':st.st_size,
                                'mtime_ns':st.st_mtime_ns,'sha256':digest_file(path)})
            elif path.is_dir():
                entries.append({'path':relative,'type':'directory'})
    return sorted(entries,key=lambda x:x['path'])


def prepare(work):
    import zstandard
    entries=resources()
    manifest=work/'resource-files.json'
    manifest.write_text(json.dumps(entries,ensure_ascii=False,indent=2)+'\n')
    manifest.chmod(0o600)
    target=work/'resources.tar.zst'
    temporary=target.with_suffix('.partial')
    with temporary.open('wb') as output:
        with zstandard.ZstdCompressor(level=3,threads=2).stream_writer(output) as compressed:
            with tarfile.open(fileobj=compressed,mode='w|') as archive:
                for index,entry in enumerate(entries):
                    path=ROOT/entry['path']
                    if entry['type']=='file':
                        st=path.stat()
                        if st.st_size!=entry['size'] or st.st_mtime_ns!=entry['mtime_ns']:
                            raise RuntimeError('Source changed while archiving: '+entry['path'])
                    archive.add(path,arcname=entry['path'],recursive=False)
                    if index and index%5000==0:
                        print('Archived',index,'entries',flush=True)
    temporary.replace(target)
    target.chmod(0o600)
    print(json.dumps({'archive':str(target),'entries':len(entries),'bytes':target.stat().st_size}),flush=True)


def bucket_for(config,profile='dutch-corpus'):
    import oss2
    data=json.loads((Path.home()/'.aliyun/config.json').read_text())
    identity=next(p for p in data['profiles'] if p['name']==profile)
    # OSS is in mainland China; do not send archival traffic through a global proxy.
    # This changes only this SDK session and retains HTTPS verification.
    session=oss2.Session()
    session.session.trust_env=False
    return oss2.Bucket(oss2.Auth(identity['access_key_id'],identity['access_key_secret']),
                       config['endpoint'],config['bucket'],connect_timeout=30,session=session)


def upload(work,path,key):
    import oss2
    config=json.loads((work/'oss-config.json').read_text())
    bucket=bucket_for(config)
    object_key=config['prefix']+'/'+key
    sha=digest_file(path)
    size=path.stat().st_size
    checkpoints=work/'oss-checkpoints';checkpoints.mkdir(exist_ok=True,mode=0o700)
    previous=[-1]
    def progress(done,total):
        block=done//(256*1024*1024)
        if block!=previous[0]:
            previous[0]=block
            print(json.dumps({'object':key,'uploaded':done,'total':total}),flush=True)
    oss2.resumable_upload(bucket,object_key,str(path),store=oss2.ResumableStore(root=str(checkpoints)),
        multipart_threshold=16*1024*1024,part_size=16*1024*1024,num_threads=8,
        progress_callback=progress,headers={'x-oss-server-side-encryption':'AES256','x-oss-meta-sha256':sha})
    head=bucket.head_object(object_key)
    if head.content_length!=size or head.headers.get('x-oss-meta-sha256')!=sha:
        raise RuntimeError('Uploaded object metadata mismatch')
    receipt={'bucket':config['bucket'],'key':object_key,'size':size,'sha256':sha,
             'etag':head.etag,'source':str(path.resolve()),'encryption':head.headers.get('x-oss-server-side-encryption')}
    receipts=work/'receipts';receipts.mkdir(exist_ok=True,mode=0o700)
    record=receipts/(hashlib.sha256(object_key.encode()).hexdigest()+'.json')
    record.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');record.chmod(0o600)
    bucket.put_object(object_key+'.sha256',sha+'  '+key+'\n',headers={'x-oss-server-side-encryption':'AES256'})
    print(json.dumps({'verified_upload':object_key,'size':size,'sha256':sha}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,default=ROOT/'local/migration-20261120')
    sub=parser.add_subparsers(dest='action',required=True)
    sub.add_parser('prepare')
    up=sub.add_parser('upload');up.add_argument('file',type=Path);up.add_argument('key')
    args=parser.parse_args()
    args.work.mkdir(parents=True,exist_ok=True,mode=0o700)
    if args.action=='prepare':prepare(args.work)
    else:upload(args.work,args.file,args.key)
