import os
import sys
import json
import re
import urllib.parse
import urllib.request
import traceback
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

# Pastikan output console aman dari UnicodeEncodeError di Windows
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Coba import requests dan feedparser jika tersedia
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

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
    "Skor Awal Bot (1-10)",
    "Catatan Awal Bot",
    "Skor Final Editorial",
    "Rekomendasi Angle Suteki",
    "Status Tindak Lanjut"
]

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
}

def clean_title(title):
    """Membersihkan imbuhan nama media di akhir judul berita."""
    if not title:
        return "Tanpa Judul"
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
        import email.utils
        parsed_tuple = email.utils.parsedate_tz(date_str)
        if parsed_tuple:
            dt = datetime.fromtimestamp(email.utils.mktime_tz(parsed_tuple))
            return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    return datetime.now().strftime("%Y-%m-%d")

def is_recent(date_str, max_days=7):
    """Memeriksa apakah tanggal artikel terbit dalam rentang hari terakhir (Recency Filter)."""
    if not date_str:
        return True
    try:
        pub_dt = datetime.strptime(date_str, "%Y-%m-%d")
        delta = datetime.now() - pub_dt
        return delta.days <= max_days
    except Exception:
        return True

def fetch_rss_feedparser(url, default_source="Google News"):
    """Mengambil feed menggunakan requests + feedparser agar tahan terhadap pemblokiran & network error."""
    articles = []
    try:
        if HAS_REQUESTS:
            resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=12)
            if resp.status_code != 200:
                print(f"[WARN] HTTP {resp.status_code} saat mengakses {url}")
                return articles
            feed = feedparser.parse(resp.content)
        else:
            feed = feedparser.parse(url)
    except Exception as e:
        print(f"[WARN] Gagal mengambil feed dari {url}: {e}")
        return articles

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
    req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
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
    """Mengumpulkan artikel dari Google News RSS query dan portal langsung secara resilient."""
    all_raw = []
    fetcher = fetch_rss_feedparser if HAS_FEEDPARSER else fetch_rss_builtin
    parser_name = "feedparser" if HAS_FEEDPARSER else "standard XML fallback"
    print(f"[*] Menggunakan parser: {parser_name}")

    # 1. Google News Queries (Dibungkus try..except per query)
    for q in GOOGLE_NEWS_QUERIES:
        try:
            encoded_query = urllib.parse.quote(q)
            url = f"https://news.google.com/rss/search?q={encoded_query}&hl=id&gl=ID&ceid=ID:id"
            print(f"[*] Menarik Google News Feed: {q}")
            items = fetcher(url, default_source="Google News")
            all_raw.extend(items)
        except Exception as e:
            print(f"[WARN] Melewati query '{q}' karena error: {e}")

    # 2. Direct Media RSS (Dibungkus try..except per media)
    for direct in DIRECT_RSS_FEEDS:
        try:
            print(f"[*] Menarik Direct RSS: {direct['source']}")
            items = fetcher(direct["url"], default_source=direct["source"])
            all_raw.extend(items)
        except Exception as e:
            print(f"[WARN] Melewati direct RSS {direct['source']} karena error: {e}")

    # Filter lokal, batas tanggal (maksimal 7 hari), & duplikasi URL di memori
    seen_urls = set()
    unique_articles = []
    today_str = datetime.now().strftime("%Y-%m-%d")

    for art in all_raw:
        url = art["link"]
        if url in seen_urls:
            continue
        seen_urls.add(url)

        # Lewati artikel usang yang terbit lebih dari 7 hari lalu
        if not is_recent(art["date"], max_days=7):
            continue

        keywords = detect_keywords(art["raw_text"])

        unique_articles.append({
            "tanggal_input": today_str,
            "sumber": art["source"],
            "judul": art["title"],
            "url": art["link"],
            "kata_kunci": keywords
        })

    print(f"[+] Total artikel segar (<= 7 hari) terkumpul: {len(unique_articles)}")
    return unique_articles

def score_articles_with_gemini(articles_to_score, api_key):
    """Memberikan scoring awal (Tier 1 Triage) menggunakan Google Gemini API gratis."""
    if not api_key or not api_key.strip():
        print("[INFO] GEMINI_API_KEY tidak ditemukan. Melewati proses AI Scoring Awal.")
        return articles_to_score

    if not articles_to_score:
        return articles_to_score

    if not HAS_REQUESTS:
        print("[WARN] Library 'requests' tidak tersedia. Melewati AI scoring.")
        return articles_to_score

    print(f"[*] Menjalankan AI Scoring Awal (Gemini Flash) untuk {len(articles_to_score)} artikel baru...")

    batch_size = 25
    clean_key = api_key.strip()

    for i in range(0, len(articles_to_score), batch_size):
        chunk = articles_to_score[i:i + batch_size]
        prompt_items = []
        for idx, art in enumerate(chunk):
            prompt_items.append(f"{idx+1}. Judul: {art['judul']} | Sumber: {art['sumber']} | Tag: {art['kata_kunci']}")

        prompt_text = (
            "Anda adalah Asisten Analis Intelijen Berita untuk Suteki Technology, perusahaan EdTech penyedia "
            "SIAKAD Cloud, Pelaporan Neo Feeder PDDIKTI, Akreditasi Kampus (BAN-PT/LAM), SPMI, dan PMB Online di Indonesia.\n\n"
            "Tugas Anda: Berikan 'Scoring Awal' (skala 1-10) untuk memfilter artikel berikut berdasarkan relevansinya terhadap bisnis Suteki Technology:\n"
            "- Skor 8-10 (Tinggi/Prioritas): Isu SIAKAD, server kampus down saat KRS/PMB, regulasi baru PDDIKTI/Neo Feeder, akreditasi kampus, atau digitalisasi tata kelola perguruan tinggi.\n"
            "- Skor 5-7 (Menengah): Isu pendidikan tinggi umum, UKT/biaya kuliah, SNPMB/PMB reguler, AI dalam pembelajaran, atau kegiatan universitas secara umum.\n"
            "- Skor 1-4 (Rendah/Abaikan): Berita seremonial wisuda, kriminal/tawuran kampus, olahraga mahasiswa, atau berita sekolah dasar/menengah.\n\n"
            "Daftar Artikel:\n" + "\n".join(prompt_items) + "\n\n"
            "Kembalikan HANYA format JSON valid berupa array of objects (tanpa markdown tambahan) dengan format persis:\n"
            "[\n"
            "  {\"id\": 1, \"skor\": 9, \"alasan\": \"Membahas implementasi SIAKAD baru dan integrasi data\"},\n"
            "  {\"id\": 2, \"skor\": 3, \"alasan\": \"Hanya kegiatan seremonial wisuda\"}\n"
            "]"
        )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={clean_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt_text}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.2
            }
        }

        try:
            resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
            if resp.status_code == 404:
                # Fallback ke gemini-1.5-flash jika model 2.5 belum aktif
                fallback_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={clean_key}"
                resp = requests.post(fallback_url, json=payload, headers={"Content-Type": "application/json"}, timeout=30)

            if resp.status_code == 200:
                data = resp.json()
                raw_reply = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed_list = json.loads(raw_reply)
                for item in parsed_list:
                    item_id = item.get("id")
                    if item_id and 1 <= item_id <= len(chunk):
                        target_art = chunk[item_id - 1]
                        target_art["skor_awal"] = item.get("skor", "")
                        target_art["alasan_awal"] = item.get("alasan", "")
                print(f"[+] Berhasil menilai batch {i//batch_size + 1} ({len(chunk)} artikel).")
            else:
                print(f"[WARN] Gemini API mengembalikan HTTP {resp.status_code}: {resp.text[:120]}")
        except Exception as e:
            print(f"[WARN] Gagal auto-scoring batch dengan Gemini: {e}")

    return articles_to_score

def extract_spreadsheet_id(raw_input):
    """Mengekstrak ID bersih dari Spreadsheet ID murni atau URL lengkap."""
    if not raw_input:
        return ""
    text = raw_input.strip()
    match = re.search(r'/d/([a-zA-Z0-9-_]+)', text)
    if match:
        return match.group(1)
    return text

def sync_to_google_sheets(articles):
    """Menyinkronkan artikel baru ke Google Sheets menggunakan Service Account."""
    if not HAS_GSPREAD:
        print("[!] Library 'gspread' atau 'google-auth' tidak terpasang. Mode Dry-Run aktif.")
        return False

    gcp_sa_key = os.getenv("GCP_SA_KEY")
    raw_sheet_input = os.getenv("SPREADSHEET_ID")
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    local_sa_file = "service_account.json"

    client = None
    bot_email = "Service Account"
    if gcp_sa_key and gcp_sa_key.strip():
        raw_key = gcp_sa_key.strip()
        if not raw_key.startswith("{"):
            print("[ERROR] Nilai secret 'GCP_SA_KEY' tidak diawali dengan '{'.")
            return False
        try:
            sa_info = json.loads(raw_key)
            bot_email = sa_info.get("client_email", bot_email)
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ]
            creds = Credentials.from_service_account_info(sa_info, scopes=scopes)
            client = gspread.authorize(creds)
            print(f"[+] Berhasil autentikasi bot: {bot_email}")
        except Exception as e:
            print(f"[ERROR] Gagal memproses JSON pada GCP_SA_KEY: {e}")
            return False
    elif os.path.exists(local_sa_file):
        try:
            client = gspread.service_account(filename=local_sa_file)
            print("[+] Berhasil autentikasi menggunakan file service_account.json lokal.")
        except Exception as e:
            print(f"[ERROR] Gagal memproses service_account.json: {e}")
            return False
    else:
        print("[INFO] Kredensial GCP_SA_KEY / service_account.json belum diatur atau kosong.")
        print("[INFO] Menjalankan dalam mode Dry-Run...")
        return False

    spreadsheet_id = extract_spreadsheet_id(raw_sheet_input)
    if not spreadsheet_id:
        print("[ERROR] Secret 'SPREADSHEET_ID' belum diisi di GitHub Repository Secrets.")
        return False

    print(f"[*] Menghubungkan ke Google Spreadsheet ID: {spreadsheet_id}")

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

        # Update header baris 1 agar selalu sesuai dengan skema terbaru (10 kolom)
        first_row = ws.row_values(1)
        if not first_row or len(first_row) < len(HEADER_COLUMNS) or first_row[5] != HEADER_COLUMNS[5]:
            print("[*] Menyesuaikan baris header tabel dengan format Two-Tier Scoring...")
            ws.update(values=[HEADER_COLUMNS], range_name="A1:J1")

        # Ambil daftar URL yang sudah ada di Kolom D (Kolom ke-4) untuk anti-duplikasi
        existing_urls = set(ws.col_values(4)[1:])
        print(f"[*] Ditemukan {len(existing_urls)} URL yang sudah ada di Google Sheet.")

        # Filter hanya artikel yang benar-benar baru
        truly_new_articles = [art for art in articles if art["url"] not in existing_urls]
        print(f"[+] Ditemukan {len(truly_new_articles)} artikel yang benar-benar baru.")

        if not truly_new_articles:
            print("[INFO] Tidak ada artikel baru yang perlu ditambahkan (semua URL sudah tercatat).")
            return True

        # Jalankan AI Scoring Awal (Gemini) HANYA untuk artikel yang baru!
        scored_articles = score_articles_with_gemini(truly_new_articles, gemini_api_key)

        new_rows = []
        for art in scored_articles:
            new_rows.append([
                art["tanggal_input"],
                art["sumber"],
                art["judul"],
                art["url"],
                art["kata_kunci"],
                art.get("skor_awal", ""),
                art.get("alasan_awal", ""),
                "",  # Skor Final Editorial (dikosongkan untuk ChatGPT)
                "",  # Rekomendasi Angle Suteki (dikosongkan untuk ChatGPT)
                "Antrean"  # Status Tindak Lanjut awal
            ])
            existing_urls.add(art["url"])

        print(f"[+] Menyimpan {len(new_rows)} artikel baru lengkap dengan Scoring Awal ke Google Sheets...")
        ws.append_rows(new_rows, value_input_option="USER_ENTERED")
        print("[OK] Sinkronisasi ke Google Sheets berhasil!")

        return True
    except gspread.exceptions.SpreadsheetNotFound:
        print("=" * 60)
        print(f"[ERROR] Spreadsheet dengan ID '{spreadsheet_id}' TIDAK DITEMUKAN atau TIDAK DAPAT DIAKSES.")
        print("[SOLUSI]:")
        print("1. Buka file Google Spreadsheet Anda di browser.")
        print(f"2. Klik tombol 'Share' (Bagikan) di pojok kanan atas.")
        print(f"3. Masukkan email bot berikut: {bot_email}")
        print("4. Atur izin akses sebagai 'Editor', lalu klik 'Kirim/Bagikan'.")
        print("=" * 60)
        return False
    except gspread.exceptions.APIError as e:
        print(f"[ERROR] Google Sheets API Error: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Terjadi kesalahan: {type(e).__name__} - {e}")
        traceback.print_exc()
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
