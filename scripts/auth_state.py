#!/usr/bin/env python3
import base64
import hashlib
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

AAD=b'ah-last-chance-auth-state-v1'
SEALED_PATH=Path('data/auth_state.enc')
DEFAULT_LOCAL_STATE=Path('/tmp/ah-last-chance-auth-state.json')


def _key(root_secret: str) -> bytes:
    if not root_secret:
        raise ValueError('AH_REFRESH_TOKEN ontbreekt voor auth-state decryptie')
    return hashlib.sha256(b'ah-last-chance-root-key-v1\x00'+root_secret.encode()).digest()


def local_state_path() -> Path:
    return Path(os.getenv('AH_TOKEN_STATE_FILE',str(DEFAULT_LOCAL_STATE)))


def restore_state(root_secret: str, sealed_path: Path=SEALED_PATH) -> dict:
    path=local_state_path()
    if path.exists():
        try:
            data=json.loads(path.read_text(encoding='utf-8'))
            if isinstance(data,dict):
                return data
        except Exception:
            pass
    if not sealed_path.exists():
        return {}
    try:
        envelope=json.loads(sealed_path.read_text(encoding='utf-8'))
        if int(envelope.get('version',0))!=1:
            return {}
        nonce=base64.urlsafe_b64decode(envelope['nonce'])
        ciphertext=base64.urlsafe_b64decode(envelope['ciphertext'])
        plain=AESGCM(_key(root_secret)).decrypt(nonce,ciphertext,AAD)
        data=json.loads(plain.decode())
        if not isinstance(data,dict):
            return {}
        path.parent.mkdir(parents=True,exist_ok=True)
        tmp=path.with_suffix(path.suffix+'.tmp')
        tmp.write_text(json.dumps(data,separators=(',',':')),encoding='utf-8')
        os.chmod(tmp,0o600)
        tmp.replace(path)
        os.chmod(path,0o600)
        return data
    except Exception:
        # A changed root secret intentionally invalidates the old envelope.
        # Production then falls back to the newly configured refresh token.
        return {}


def seal_state_text(root_secret: str) -> str:
    path=local_state_path()
    if not path.exists():
        return ''
    data=json.loads(path.read_text(encoding='utf-8'))
    refresh=str(data.get('refreshToken') or '').strip()
    if not refresh:
        return ''
    payload=json.dumps({'refreshToken':refresh},separators=(',',':')).encode()
    nonce=os.urandom(12)
    ciphertext=AESGCM(_key(root_secret)).encrypt(nonce,payload,AAD)
    return json.dumps({
        'version':1,
        'algorithm':'AES-256-GCM',
        'nonce':base64.urlsafe_b64encode(nonce).decode(),
        'ciphertext':base64.urlsafe_b64encode(ciphertext).decode(),
    },separators=(',',':'))+'\n'


def self_test():
    import tempfile
    old=os.environ.get('AH_TOKEN_STATE_FILE')
    try:
        with tempfile.TemporaryDirectory() as td:
            state=Path(td)/'state.json'
            sealed=Path(td)/'sealed.enc'
            os.environ['AH_TOKEN_STATE_FILE']=str(state)
            state.write_text(json.dumps({'refreshToken':'rotated-token'}),encoding='utf-8')
            os.chmod(state,0o600)
            text=seal_state_text('root-token')
            sealed.write_text(text,encoding='utf-8')
            state.unlink()
            restored=restore_state('root-token',sealed)
            assert restored.get('refreshToken')=='rotated-token'
            state.unlink()
            assert restore_state('different-root',sealed)=={}
        print('auth-state encryption self-test: PASS')
    finally:
        if old is None:
            os.environ.pop('AH_TOKEN_STATE_FILE',None)
        else:
            os.environ['AH_TOKEN_STATE_FILE']=old


if __name__=='__main__':
    self_test()
