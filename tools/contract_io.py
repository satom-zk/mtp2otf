"""Atomically hand generated data to the next process."""
import hashlib
import json
import os
from pathlib import Path
import tempfile


def write_contract(path, payload):
    path = Path(path)
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8')
    expected = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    try:
        fd, temporary = tempfile.mkstemp(
            prefix=path.name + '.', suffix='.tmp', dir=path.parent
        )
    except OSError as exc:
        raise ValueError(f'contract write incomplete: {path}: {exc}') from exc
    temporary = Path(temporary)
    try:
        try:
            with os.fdopen(fd, 'wb') as stream:
                written = stream.write(data)
                if written != len(data):
                    raise ValueError(
                        f'contract write incomplete: {path}: '
                        f'expected {expected}, write returned {written}'
                    )
        except OSError as exc:
            raise ValueError(
                f'contract write incomplete: {path}: expected {expected}: '
                f'{exc}'
            ) from exc
        try:
            saved = temporary.read_bytes()
            if saved != data:
                actual = {
                    'bytes': len(saved),
                    'sha256': hashlib.sha256(saved).hexdigest()
                }
                raise ValueError(
                    f'contract saved content mismatch: {path}: '
                    f'expected {expected}, actual {actual}'
                )
            os.replace(temporary, path)
        except OSError as exc:
            raise ValueError(
                f'contract saved content mismatch: {path}: {exc}'
            ) from exc
    finally:
        temporary.unlink(missing_ok=True)
    return expected


def verify_contract(path, expected):
    path = Path(path)
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ValueError(
            f'contract changed before consumer: {path}: {exc}'
        ) from exc
    actual = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    if actual != expected:
        raise ValueError(
            f'contract changed before consumer: {path}: '
            f'expected {expected}, actual {actual}'
        )
    return data
