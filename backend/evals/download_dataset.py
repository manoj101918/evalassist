"""Download the evaluation dataset (Mendeley Data sf3kvjwknt, CC BY 4.0).

The dataset is a single 145 MB zip. Instead of downloading all of it (which kept timing out on
a slow connection), this reads the zip's index with HTTP range requests and fetches only the
files we need: the text/CSV files and the raw student PDFs (not the teacher-annotated copies).
Resumable: files already on disk are skipped. Run from backend/:

    python -m evals.download_dataset            # everything
    python -m evals.download_dataset --limit 5  # first 5 students only
"""
import argparse
import io
import sys
import time
import urllib.error
import urllib.request
import zipfile

from evals.dataset import DATA_DIR, PDF_DIR

ZIP_API = "https://data.mendeley.com/public-api/zip/sf3kvjwknt/download/1"
UA = {"User-Agent": "Mozilla/5.0 (EvalAssist dataset downloader)"}
TEXT_FILES = ("Question.txt", "answerkey.txt", "Teacher_manual_marks_Anonymized.csv",
              "Student_MCQ.csv", "README.md")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _presigned_url() -> str:
    """The API redirects to a short-lived S3 link; fetch a fresh one when it expires."""
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        opener.open(urllib.request.Request(ZIP_API, headers=UA), timeout=60)
    except urllib.error.HTTPError as exc:
        if exc.code in (301, 302, 303, 307):
            return exc.headers["Location"]
        raise
    raise RuntimeError("expected a redirect to the zip file")


class RemoteZipFile(io.RawIOBase):
    """A seekable file over HTTP range requests, retrying the network blips we see often."""

    def __init__(self):
        self.url = _presigned_url()
        self.pos = 0
        self.size = int(self._get(0, 0, head=True))

    def _get(self, start: int, end: int, head: bool = False):
        for attempt in range(10):
            try:
                req = urllib.request.Request(self.url, headers={**UA, "Range": f"bytes={start}-{end}"})
                with urllib.request.urlopen(req, timeout=120) as r:
                    return r.headers["Content-Range"].split("/")[1] if head else r.read()
            except urllib.error.HTTPError as exc:
                if exc.code == 403:  # presigned link expired
                    self.url = _presigned_url()
                    continue
                raise
            except OSError as exc:
                print(f"  network error ({exc}); retrying", file=sys.stderr)
                time.sleep(2 + 2 * attempt)
        raise RuntimeError("too many network errors")

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=0):
        self.pos = {0: offset, 1: self.pos + offset, 2: self.size + offset}[whence]
        return self.pos

    def readinto(self, buffer):
        if self.pos >= self.size or len(buffer) == 0:
            return 0
        end = min(self.pos + len(buffer), self.size) - 1
        data = self._get(self.pos, end)
        buffer[:len(data)] = data
        self.pos += len(data)
        return len(data)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="only the first N students")
    args = ap.parse_args()

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    archive = zipfile.ZipFile(io.BufferedReader(RemoteZipFile(), buffer_size=1 << 20))
    members = archive.namelist()

    for name in TEXT_FILES:
        dest = DATA_DIR / name
        src = next((m for m in members if m.endswith("/" + name)), None)
        if src and not dest.exists():
            dest.write_bytes(archive.read(src))
            print("saved", dest.name)

    pdfs = sorted((m for m in members if "/Student_Pdf/" in m and m.endswith(".pdf")),
                  key=lambda m: int(m.rsplit("_", 1)[1].split(".")[0]))
    for src in pdfs[: args.limit]:
        dest = PDF_DIR / src.rsplit("/", 1)[1]
        if dest.exists():
            continue
        for attempt in range(3):
            try:
                dest.write_bytes(archive.read(src))
                print("saved", dest.name, dest.stat().st_size // 1024, "KB", flush=True)
                break
            except Exception as exc:  # noqa: BLE001 - keep going with the other files
                print(f"  failed {dest.name} ({exc}); attempt {attempt + 1}/3", file=sys.stderr)
                if dest.exists():
                    dest.unlink()


if __name__ == "__main__":
    main()
