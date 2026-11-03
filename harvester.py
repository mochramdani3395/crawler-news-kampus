import os
import sys
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

# Pastikan output console aman dari UnicodeEncodeError di Windows
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Coba import feedparser jika tersedia, jika tidak gunakan fallback XML parser
try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False

# Coba import gspread jika tersedia
try:
    import gspread
    from google.oauth2.service_account import Credentials
    HAS_GSPREAD = True
except ImportError:
    HAS_GSPREAD = False

# ==========================================
# KONFIGURASI TARGET SUTEKI TECHNOLOGY
# ==========================================

# Query pencarian di Google News RSS (Bahasa Indonesia)
GOOGLE_NEWS_QUERIES = [
    'siakad OR "sistem informasi akademik" OR "krs online"',
    'pddikti OR "neo feeder" OR "feeder dikti" OR "penonaktifan prodi"',
    '"akreditasi kampus" OR "ban-pt" OR "lam-infokom" OR "lamdik" OR "borang akreditasi" OR "spmi"',
    '"kemdiktisaintek" OR "kemendikbudristek" OR "lldikti" OR "perguruan tinggi swasta"',
    '"server kampus down" OR "snpmb" OR "pmb online" OR "biaya kuliah perguruan tinggi"'
]

# RSS Feed langsung dari portal berita nasional (Kanal Edukasi)
DIRECT_RSS_FEEDS = [
    {"source": "Detik Edu", "url": "https://rss.detik.com/index.php/detikedu"},
    {"source": "Antara Humaniora", "url": "https://www.antaranews.com/rss/humaniora.xml"},
    {"source": "Sindonews Edukasi", "url": "https://edukasi.sindonews.com/rss"}
]

# Pemetaan Tag Kata Kunci untuk Kolom 'Kata Kunci Terdeteksi'
KEYWORD_RULES = [
    ("SIAKAD & Sistem Kampus", [r"\bsiakad\b", r"\bkrs\b", r"sistem informasi akademik", r"server.*down", r"portal mahasiswa"]),
    ("PDDIKTI & Neo Feeder", [r"\bpddikti\b", r"neo feeder", r"\bfeeder\b", r"sinkronisasi data", r"penonaktifan prodi"]),
    ("Akreditasi & SPMI", [r"akreditasi", r"\bban-pt\b", r"lam-infokom", r"lamdik", r"borang", r"\bspmi\b", r"\bipepa\b"]),
    ("Regulasi & Kementerian", [r"kemdiktisaintek", r"kemendikbud", r"\blldikti\b", r"perguruan tinggi swasta", r"\bpts\b", r"\bptn\b"]),
    ("PMB & Keuangan Kampus", [r"\bsnpmb\b", r"\bpmb\b", r"\bukt\b", r"biaya kuliah", r"mahasiswa baru"])
]

HEADER_COLUMNS = [
    "Tanggal Input",
    "Sumber Media",
    "Judul Berita",
    "URL Berita",
    "Kata Kunci Terdeteksi",
    "Skor Relevansi (1-10)",
    "Skor Urgensi (1-10)",
    "Rekomendasi Angle Konten",
    "Status Tindak Lanjut"
]

def clean_title(title):
    """Membersihkan imbuhan nama media di akhir judul berita."""
    if not title:
        return "Tanpa Judul"
    # Menghapus akhiran seperti ' - Detikcom', ' - Kompas.com', ' | Tempo.co'
    cleaned = re.sub(r'\s*[-|–—]\s*([A-Za-z0-9\s.]+)(com|co\.id|id)?\s*$', '', title, flags=re.IGNORECASE)
    return cleaned.strip()

def detect_keywords(text):
    """Mendeteksi kata kunci relevan untuk ekosistem Suteki."""
    found_tags = []
    text_lower = text.lower()
    for tag_name, patterns in KEYWORD_RULES:
        for pat in patterns:
            if re.search(pat, text_lower):
                found_tags.append(tag_name)
                break
    return ", ".join(found_tags) if found_tags else "Pendidikan Umum"

def parse_date(date_str):
    """Menyeragamkan tanggal menjadi format YYYY-MM-DD."""
    if not date_str:
        return datetime.now().strftime("%Y-%m-%d")
    try:
        # Coba parsing RFC 2822 (umum di RSS)
        import email.utils
        parsed_tuple = email.utils.parsedate_tz(date_str)
        if parsed_tuple:
            dt = datetime.fromtimestamp(email.utils.mktime_tz(parsed_tuple))
            return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    return datetime.now().strftime("%Y-%m-%d")

def fetch_rss_feedparser(url, default_source="Google News"):
    """Mengambil feed menggunakan library feedparser."""
    articles = []
    feed = feedparser.parse(url)
    for entry in feed.entries:
        link = entry.get("link", "").strip()
        title = entry.get("title", "").strip()
        if not link or not title:
            continue
            
        source_name = default_source
        if hasattr(entry, "source") and isinstance(entry.source, dict) and entry.source.get("title"):
            source_name = entry.source.get("title")
        elif " - " in title:
            parts = title.rsplit(" - ", 1)
            if len(parts) > 1 and len(parts[1]) < 30:
                source_name = parts[1].strip()

        pub_date = parse_date(entry.get("published", entry.get("updated", "")))
        
        articles.append({
            "title": clean_title(title),
            "link": link,
            "source": source_name,
            "date": pub_date,
            "raw_text": f"{title} {entry.get('summary', '')}"
        })
    return articles

def fetch_rss_builtin(url, default_source="Google News"):
    """Fallback parser menggunakan standard library Python jika feedparser belum diinstall."""
    articles = []
    req = urllib.request.Request(
        url, 
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            xml_data = response.read()
        root = ET.fromstring(xml_data)
        for item in root.findall(".//item"):
            title_el = item.find("title")
            link_el = item.find("link")
            pub_date_el = item.find("pubDate")
            source_el = item.find("source")

            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            link = link_el.text.strip() if link_el is not None and link_el.text else ""
            if not title or not link:
                continue

            source_name = default_source
            if source_el is not None and source_el.text:
                source_name = source_el.text.strip()
            elif " - " in title:
                parts = title.rsplit(" - ", 1)
                if len(parts) > 1 and len(parts[1]) < 30:
                    source_name = parts[1].strip()

            pub_date = parse_date(pub_date_el.text if pub_date_el is not None else "")
            desc_el = item.find("description")
            desc_text = desc_el.text if desc_el is not None and desc_el.text else ""

            articles.append({
                "title": clean_title(title),
                "link": link,
                "source": source_name,
                "date": pub_date,
                "raw_text": f"{title} {desc_text}"
            })
    except Exception as e:
        print(f"[WARN] Gagal mengambil XML {url}: {e}")
    return articles

def collect_all_articles():
    """Mengumpulkan artikel dari Google News RSS query dan portal langsung."""
    all_raw = []
    fetcher = fetch_rss_feedparser if HAS_FEEDPARSER else fetch_rss_builtin
    parser_name = "feedparser" if HAS_FEEDPARSER else "standard XML fallback"
    print(f"[*] Menggunakan parser: {parser_name}")

    # 1. Google News Queries
    for q in GOOGLE_NEWS_QUERIES:
        encoded_query = urllib.parse.quote(q)
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl=id&gl=ID&ceid=ID:id"
        print(f"[*] Menarik Google News Feed: {q}")
        items = fetcher(url, default_source="Google News")
        all_raw.extend(items)

    # 2. Direct Media RSS
    for direct in DIRECT_RSS_FEEDS:
        print(f"[*] Menarik Direct RSS: {direct['source']}")
        items = fetcher(direct["url"], default_source=direct["source"])
        all_raw.extend(items)

    # Filter lokal & duplikasi URL di memori
    seen_urls = set()
    unique_articles = []
    today_str = datetime.now().strftime("%Y-%m-%d")

    for art in all_raw:
        url = art["link"]
        if url in seen_urls:
            continue
        seen_urls.add(url)

        keywords = detect_keywords(art["raw_text"])

        # Masukkan ke daftar artikel siap ekspor
        unique_articles.append({
            "tanggal_input": today_str,
            "sumber": art["source"],
            "judul": art["title"],
            "url": art["link"],
            "kata_kunci": keywords
        })

    print(f"[+] Total artikel unik terkumpul: {len(unique_articles)}")
    return unique_articles

def sync_to_google_sheets(articles):
    """Menyinkronkan artikel baru ke Google Sheets menggunakan Service Account."""
    if not HAS_GSPREAD:
        print("[!] Library 'gspread' atau 'google-auth' tidak terpasang. Mode Dry-Run aktif.")
        return False

    gcp_sa_key = os.getenv("GCP_SA_KEY")
    spreadsheet_id = os.getenv("SPREADSHEET_ID")
    local_sa_file = "service_account.json"

    client = None
    if gcp_sa_key:
        try:
            sa_info = json.loads(gcp_sa_key)
            scopes = ["https://www.googleapis.com/auth/spreadsheets"]
            creds = Credentials.from_service_account_info(sa_info, scopes=scopes)
            client = gspread.authorize(creds)
            print("[+] Berhasil autentikasi menggunakan GCP_SA_KEY dari Secrets.")
        except Exception as e:
            print(f"[ERROR] Gagal memproses GCP_SA_KEY: {e}")
            return False
    elif os.path.exists(local_sa_file):
        try:
            client = gspread.service_account(filename=local_sa_file)
            print("[+] Berhasil autentikasi menggunakan file service_account.json lokal.")
        except Exception as e:
            print(f"[ERROR] Gagal memproses service_account.json: {e}")
            return False
    else:
        print("[INFO] Kredensial GCP_SA_KEY / service_account.json belum diatur.")
        print("[INFO] Menjalankan dalam mode Dry-Run...")
        return False

    if not spreadsheet_id:
        print("[ERROR] SPREADSHEET_ID belum ditentukan di environment variables.")
        return False

    try:
        sh = client.open_by_key(spreadsheet_id)
        
        # Cari worksheet 'News_Radar' atau buat jika belum ada
        worksheet_title = "News_Radar"
        try:
            ws = sh.worksheet(worksheet_title)
        except gspread.WorksheetNotFound:
            print(f"[*] Worksheet '{worksheet_title}' belum ada. Membuat worksheet baru...")
            ws = sh.add_worksheet(title=worksheet_title, rows=500, cols=15)
            ws.append_row(HEADER_COLUMNS)

        # Cek apakah header sudah ada di baris pertama
        first_row = ws.row_values(1)
        if not first_row or first_row[0] != HEADER_COLUMNS[0]:
            print("[*] Mengisi baris header tabel...")
            ws.insert_row(HEADER_COLUMNS, 1)

        # Ambil daftar URL yang sudah ada di Kolom D (Kolom ke-4) untuk anti-duplikasi
        existing_urls = set(ws.col_values(4)[1:])  # Lewati baris header
        print(f"[*] Ditemukan {len(existing_urls)} URL yang sudah ada di Google Sheet.")

        new_rows = []
        for art in articles:
            if art["url"] not in existing_urls:
                new_rows.append([
                    art["tanggal_input"],
                    art["sumber"],
                    art["judul"],
                    art["url"],
                    art["kata_kunci"],
                    "",  # Skor Relevansi (dikosongkan untuk ChatGPT)
                    "",  # Skor Urgensi (dikosongkan untuk ChatGPT)
                    "",  # Rekomendasi Angle (dikosongkan untuk ChatGPT)
                    "Antrean"  # Status Tindak Lanjut awal
                ])
                existing_urls.add(art["url"])

        if new_rows:
            print(f"[+] Menyimpan {len(new_rows)} artikel baru ke Google Sheets...")
            ws.append_rows(new_rows, value_input_option="USER_ENTERED")
            print("[OK] Sinkronisasi ke Google Sheets berhasil!")
        else:
            print("[INFO] Tidak ada artikel baru yang perlu ditambahkan (semua URL sudah tercatat).")

        return True
    except Exception as e:
        print(f"[ERROR] Terjadi kesalahan saat komunikasi dengan Google Sheets: {e}")
        return False

def main():
    print("=" * 60)
    print("      SUTEKI NEWS RADAR - AUTOMATED URL HARVESTER")
    print("=" * 60)

    articles = collect_all_articles()

    # Coba sinkronisasi ke Google Sheets
    synced = sync_to_google_sheets(articles)

    # Jika belum tersambung ke Google Sheets (Dry-run), simpan pratinjau lokal
    if not synced:
        preview_file = "preview_radar.json"
        with open(preview_file, "w", encoding="utf-8") as f:
            json.dump(articles, f, indent=2, ensure_ascii=False)
        print(f"[OK] Hasil penarikan disimpan ke pratinjau lokal: '{preview_file}'")
        print(f"[i] Contoh 3 artikel pertama:")
        for idx, item in enumerate(articles[:3], 1):
            print(f"    {idx}. [{item['sumber']}] {item['judul']}")
            print(f"       Tag: {item['kata_kunci']}")
            print(f"       URL: {item['url']}")

if __name__ == "__main__":
    main()
