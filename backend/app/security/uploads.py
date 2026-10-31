"""Bounded upload spooling for administrator document uploads."""

from tempfile import SpooledTemporaryFile
from typing import BinaryIO, Tuple


class UploadLimitError(ValueError):
    pass


async def spool_limited_upload(
    upload,
    *,
    max_file_bytes: int,
    remaining_total_bytes: int,
    chunk_size: int = 64 * 1024,
) -> Tuple[BinaryIO, int, bytes]:
    """Copy an UploadFile incrementally into a bounded in-memory/disk spool."""
    spool = SpooledTemporaryFile(max_size=min(max_file_bytes, 8 * 1024 * 1024), mode="w+b")
    size = 0
    prefix = bytearray()
    try:
        while True:
            chunk = await upload.read(chunk_size)
            if not chunk:
                break
            size += len(chunk)
            if size > max_file_bytes:
                raise UploadLimitError(f"File exceeds the {max_file_bytes}-byte per-file limit.")
            if size > remaining_total_bytes:
                raise UploadLimitError("Upload batch exceeds the configured total size limit.")
            if len(prefix) < 2048:
                prefix.extend(chunk[:2048 - len(prefix)])
            spool.write(chunk)
        if size == 0:
            raise UploadLimitError("Uploaded file is empty.")
        spool.seek(0)
        return spool, size, bytes(prefix)
    except Exception:
        spool.close()
        raise
