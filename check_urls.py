from __future__ import annotations

import argparse
import random
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Tuple

import pandas as pd
import requests

DEFAULT_INPUT = "input/termekek.xlsx"
DEFAULT_OUTPUT_DIR = "output"
DEFAULT_URL_COLUMN = "URL"
DEFAULT_TIMEOUT = 8
DEFAULT_CONNECT_TIMEOUT = 4
DEFAULT_MIN_DELAY = 1.5
DEFAULT_MAX_DELAY = 2.5
DEFAULT_SAVE_EVERY = 25
DEFAULT_MAX_RUNTIME_MINUTES = 320

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Shoprenter URL ellenőrző: élő oldal vagy 404 / egyéb hiba."
    )
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Bemeneti Excel/CSV fájl útvonala")
    parser.add_argument("--url-column", default=DEFAULT_URL_COLUMN, help="Az URL-eket tartalmazó oszlop neve")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Kimeneti mappa")
    parser.add_argument("--min-delay", type=float, default=DEFAULT_MIN_DELAY, help="Minimum várakozás két kérés között (mp)")
    parser.add_argument("--max-delay", type=float, default=DEFAULT_MAX_DELAY, help="Maximum várakozás két kérés között (mp)")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Olvasási timeout másodpercben")
    parser.add_argument("--connect-timeout", type=int, default=DEFAULT_CONNECT_TIMEOUT, help="Kapcsolódási timeout másodpercben")
    parser.add_argument("--save-every", type=int, default=DEFAULT_SAVE_EVERY, help="Részmentés ennyi soronként")
    parser.add_argument(
        "--max-runtime-minutes",
        type=int,
        default=DEFAULT_MAX_RUNTIME_MINUTES,
        help="Kontrollált leállás ennyi perc után; 0 esetén nincs korlát",
    )
    parser.add_argument(
        "--use-head",
        action="store_true",
        help="Először HEAD kérés használata; alapból közvetlen GET fut",
    )
    # Visszafelé kompatibilis, rejtett kapcsoló a korábbi futtatóparancsokhoz.
    parser.add_argument("--no-head", action="store_false", dest="use_head", help=argparse.SUPPRESS)
    return parser


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": BROWSER_UA})
    return session


def read_input_file(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if suffix == ".csv":
        try:
            return pd.read_csv(path, encoding="utf-8-sig")
        except UnicodeDecodeError:
            return pd.read_csv(path, encoding="latin1")
    raise ValueError(f"Nem támogatott fájltípus: {suffix}")


def normalize_url(value: object) -> str:
    if value is None:
        return ""
    if pd.isna(value):
        return ""
    return str(value).strip()


def needs_get_fallback(status_code: int) -> bool:
    return status_code in {301, 302, 303, 307, 308, 403, 405, 500}


def perform_request(
    session: requests.Session,
    url: str,
    connect_timeout: int,
    read_timeout: int,
    use_head: bool,
) -> Tuple[str, str, str, str, str]:
    timeout = (connect_timeout, read_timeout)

    try:
        method_used = "GET"

        if use_head:
            method_used = "HEAD"
            response = session.head(url, timeout=timeout, allow_redirects=True)

            if needs_get_fallback(response.status_code):
                response.close()
                method_used = "HEAD->GET"
                response = session.get(url, timeout=timeout, allow_redirects=True, stream=True)
        else:
            response = session.get(url, timeout=timeout, allow_redirects=True, stream=True)

        status_code = str(response.status_code)
        final_url = response.url or ""
        result = "átirányítás" if response.history else classify_status_code(response.status_code)
        response.close()
        return status_code, final_url, result, "", method_used

    except requests.RequestException as exc:
        error_text = f"{type(exc).__name__}: {exc}"
        return "", "", "hiba", error_text, ""


def classify_status_code(status_code: int) -> str:
    if 200 <= status_code < 300:
        return "élő"
    if 300 <= status_code < 400:
        return "átirányítás"
    if status_code in {404, 410}:
        return "404 / nem él"
    if status_code == 429:
        return "rate limited"
    if 400 <= status_code < 500:
        return "kliens hiba"
    if 500 <= status_code < 600:
        return "szerver hiba"
    return "egyéb"


def save_results(df: pd.DataFrame, output_xlsx: Path, output_csv: Path) -> None:
    output_xlsx.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(output_xlsx, index=False)
    df.to_csv(output_csv, index=False, encoding="utf-8-sig")


def main() -> int:
    args = build_parser().parse_args()

    if args.min_delay <= 0 or args.max_delay <= 0:
        print("A késleltetésnek pozitív számnak kell lennie.", file=sys.stderr)
        return 2

    if args.min_delay > args.max_delay:
        print("A min-delay nem lehet nagyobb, mint a max-delay.", file=sys.stderr)
        return 2

    if args.timeout <= 0 or args.connect_timeout <= 0:
        print("A timeout értékeknek pozitív számnak kell lenniük.", file=sys.stderr)
        return 2

    if args.max_runtime_minutes < 0:
        print("A max-runtime-minutes nem lehet negatív.", file=sys.stderr)
        return 2

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"A bemeneti fájl nem található: {input_path}", file=sys.stderr)
        return 2

    try:
        df = read_input_file(input_path)
    except Exception as exc:
        print(f"Nem sikerült beolvasni a bemeneti fájlt: {exc}", file=sys.stderr)
        return 2

    if args.url_column not in df.columns:
        print(
            f"A(z) '{args.url_column}' oszlop nem található a fájlban. Elérhető oszlopok: {list(df.columns)}",
            file=sys.stderr,
        )
        return 2

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_dir = Path(args.output_dir)
    output_xlsx = output_dir / f"eredmenyek_{timestamp}.xlsx"
    output_csv = output_dir / f"eredmenyek_{timestamp}.csv"

    work_df = df.copy()
    work_df["Ellenorzott_URL"] = work_df[args.url_column].map(normalize_url)
    work_df["Status_Code"] = ""
    work_df["Vegso_URL"] = ""
    work_df["Eredmeny"] = ""
    work_df["Hiba"] = ""
    work_df["Mod"] = ""

    total = len(work_df)
    if total == 0:
        print("A bemeneti fájl üres.")
        save_results(work_df, output_xlsx, output_csv)
        return 0

    session = make_session()
    started_at = time.monotonic()
    stop_requested = False

    def request_stop(signum: int, _frame: object) -> None:
        nonlocal stop_requested
        stop_requested = True
        print(f"Leállítási jel érkezett ({signum}); részleges eredmény mentése következik.")

    previous_sigterm_handler = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM, request_stop)
    print(f"Ellenőrzés indul: {total} URL")
    print(f"Bemenet: {input_path}")
    print(f"Kimenet: {output_xlsx}")

    completed = 0
    stopped_early = False

    try:
        for idx, url in enumerate(work_df["Ellenorzott_URL"], start=1):
            runtime_limit_reached = (
                args.max_runtime_minutes > 0
                and time.monotonic() - started_at >= args.max_runtime_minutes * 60
            )
            if stop_requested or runtime_limit_reached:
                stopped_early = True
                reason = "leállítási kérés" if stop_requested else "futási időkorlát"
                print(f"Kontrollált leállás: {reason}; {completed}/{total} sor készült el.")
                break

            if not url:
                work_df.at[idx - 1, "Eredmeny"] = "üres URL"
                work_df.at[idx - 1, "Hiba"] = "Az URL mező üres"
                print(f"[{idx}/{total}] üres URL")
                completed = idx
                continue

            status_code, final_url, result, error_text, method_used = perform_request(
                session=session,
                url=url,
                connect_timeout=args.connect_timeout,
                read_timeout=args.timeout,
                use_head=args.use_head,
            )

            work_df.at[idx - 1, "Status_Code"] = status_code
            work_df.at[idx - 1, "Vegso_URL"] = final_url
            work_df.at[idx - 1, "Eredmeny"] = result
            work_df.at[idx - 1, "Hiba"] = error_text
            work_df.at[idx - 1, "Mod"] = method_used

            print(f"[{idx}/{total}] {url} -> {status_code or 'hiba'} | {result}")
            completed = idx

            if args.save_every > 0 and idx % args.save_every == 0:
                save_results(work_df, output_xlsx, output_csv)
                print(f"Részmentés kész: {idx} sor feldolgozva")

            if idx < total:
                time.sleep(random.uniform(args.min_delay, args.max_delay))

    finally:
        signal.signal(signal.SIGTERM, previous_sigterm_handler)
        session.close()

    save_results(work_df, output_xlsx, output_csv)
    if stopped_early:
        print(f"Részleges eredmény elkészült: {completed}/{total} sor feldolgozva.")
    else:
        print("Kész.")
    print(f"Excel eredményfájl: {output_xlsx}")
    print(f"CSV eredményfájl: {output_csv}")
    return 3 if stopped_early else 0


if __name__ == "__main__":
    raise SystemExit(main())
