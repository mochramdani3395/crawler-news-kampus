import os
import sys
import json
import re
import urllib.parse
import urllib.request
import traceback
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

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

# Skema Standar 12 Kolom Suteki News Radar
HEADER_COLUMNS = [
    "Tanggal Terbit",
    "Tanggal Crawl",
    "Sumber Media",
    "Judul Berita",
    "Cuplikan Berita",
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

_CACHED_MODELS = None

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

def parse_date(date_val):
    """Menyeragamkan tanggal posting artikel menjadi format YYYY-MM-DD HH:MM (Waktu Indonesia Barat/WIB)."""
    try:
        wib_tz = timezone(timedelta(hours=7))
        if not date_val:
            return datetime.now(wib_tz).strftime("%Y-%m-%d %H:%M")

        # 1. Jika dari feedparser (struct_time)
        import time
        if isinstance(date_val, time.struct_time):
            try:
                dt_utc = datetime(*date_val[:6], tzinfo=timezone.utc)
                return dt_utc.astimezone(wib_tz).strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass

        if isinstance(date_val, str):
            date_str = date_val.strip()
            if not date_str:
                return datetime.now(wib_tz).strftime("%Y-%m-%d %H:%M")

            # 2. Coba RFC 2822 (Standar Google News / RSS pubDate)
            try:
                import email.utils
                dt = email.utils.parsedate_to_datetime(date_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(wib_tz).strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass

            # 3. Coba ISO 8601 (Atom / Direct Media Feeds)
            try:
                clean_iso = date_str.replace("Z", "+00:00")
                dt = datetime.fromisoformat(clean_iso)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(wib_tz).strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass

            # 4. Fallback jika diawali format YYYY-MM-DD
            try:
                dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
                return dt.strftime("%Y-%m-%d")
            except Exception:
                pass

        return datetime.now(wib_tz).strftime("%Y-%m-%d %H:%M")
    except Exception:
        try:
            return datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return datetime.now().strftime("%Y-%m-%d %H:%M")

def is_recent(date_str, max_days=7):
    """Memeriksa apakah tanggal artikel terbit dalam rentang hari terakhir (Recency Filter)."""
    if not date_str:
        return True
    try:
        pub_dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
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

        pub_val = entry.get("published_parsed") or entry.get("published") or entry.get("updated_parsed") or entry.get("updated")
        pub_date = parse_date(pub_val)

        # Ambil cuplikan atau deskripsi awal dari feed jika tersedia
        raw_desc = entry.get("summary", "") or entry.get("description", "")
        clean_desc = re.sub(r'<[^>]+>', ' ', raw_desc).strip()
        clean_desc = re.sub(r'\s+', ' ', clean_desc)
        snippet = ""
        if clean_desc and len(clean_desc) > (len(title) + 20) and not clean_desc.endswith("&nbsp;"):
            snippet = clean_desc[:350]
        
        articles.append({
            "title": clean_title(title),
            "link": link,
            "source": source_name,
            "date": pub_date,
            "snippet": snippet,
            "raw_text": f"{title} {clean_desc}"
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

            pub_val = pub_date_el.text if pub_date_el is not None else ""
            pub_date = parse_date(pub_val)
            desc_el = item.find("description")
            desc_text = desc_el.text if desc_el is not None and desc_el.text else ""
            clean_desc = re.sub(r'<[^>]+>', ' ', desc_text).strip()
            clean_desc = re.sub(r'\s+', ' ', clean_desc)
            snippet = ""
            if clean_desc and len(clean_desc) > (len(title) + 20):
                snippet = clean_desc[:350]

            articles.append({
                "title": clean_title(title),
                "link": link,
                "source": source_name,
                "date": pub_date,
                "snippet": snippet,
                "raw_text": f"{title} {clean_desc}"
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

    print(f"[+] Total mentah artikel dari seluruh feed: {len(all_raw)}")

    # Filter lokal, batas tanggal (maksimal 7 hari), & duplikasi URL di memori
    seen_urls = set()
    unique_articles = []
    today_str = datetime.now().strftime("%Y-%m-%d")

    for art in all_raw:
        url = art["link"]
        if url in seen_urls:
            continue
        seen_urls.add(url)

        # Lewati artikel usang yang terbit lebih dari 7 hari lalu untuk entri baru
        if not is_recent(art["date"], max_days=7):
            continue

        keywords = detect_keywords(art["raw_text"])

        unique_articles.append({
            "tanggal_terbit": art["date"],
            "tanggal_crawl": today_str,
            "sumber": art["source"],
            "judul": art["title"],
            "cuplikan": art.get("snippet", ""),
            "url": art["link"],
            "kata_kunci": keywords
        })

    print(f"[+] Total artikel segar (<= 7 hari) terkumpul: {len(unique_articles)}")
    return unique_articles, all_raw

def get_candidate_models(api_key):
    """Mendeteksi daftar model Flash yang aktif untuk akun ini dalam urutan prioritas."""
    global _CACHED_MODELS
    if _CACHED_MODELS:
        return _CACHED_MODELS

    preferred_order = [
        "gemini-3.8-flash",
        "gemini-3.5-flash",
        "gemini-3.1-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-flash-latest"
    ]
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key.strip()}"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            models_data = resp.json().get("models", [])
            active_flashes = set()
            for m in models_data:
                name = m.get("name", "").replace("models/", "")
                methods = m.get("supportedGenerationMethods", [])
                if "generateContent" in methods and "flash" in name.lower() and not any(x in name for x in ["tts", "image", "2.5"]):
                    active_flashes.add(name)
            
            ordered = [m for m in preferred_order if m in active_flashes]
            for m in active_flashes:
                if m not in ordered:
                    ordered.append(m)
            if ordered:
                print(f"[*] Daftar model AI prioritas siap pakai: {ordered[:4]}")
                _CACHED_MODELS = ordered
                return ordered
    except Exception as e:
        print(f"[WARN] Gagal mendeteksi daftar model: {e}")

    fallback = ["gemini-3.8-flash", "gemini-3.5-flash", "gemini-flash-lite-latest", "gemini-flash-latest"]
    _CACHED_MODELS = fallback
    return fallback

def score_articles_with_gemini(articles_to_score, api_key):
    """Memberikan scoring awal (Tier 1 Triage) & ringkasan 1 paragraf menggunakan Google Gemini API."""
    if not api_key or not api_key.strip():
        print("[INFO] GEMINI_API_KEY tidak ditemukan. Melewati proses AI Scoring Awal.")
        return articles_to_score

    if not articles_to_score:
        return articles_to_score

    if not HAS_REQUESTS:
        print("[WARN] Library 'requests' tidak tersedia. Melewati AI scoring.")
        return articles_to_score

    clean_key = api_key.strip()
    candidate_models = get_candidate_models(clean_key)

    batch_size = 25

    for i in range(0, len(articles_to_score), batch_size):
        chunk = articles_to_score[i:i + batch_size]
        prompt_items = []
        for idx, art in enumerate(chunk):
            hint = f" | Cuplikan: {art.get('cuplikan', '')[:100]}" if art.get("cuplikan") else ""
            prompt_items.append(f"{idx+1}. Judul: {art['judul']} | Sumber: {art['sumber']} | Tag: {art['kata_kunci']}{hint}")

        prompt_text = (
            "Anda adalah Asisten Analis Intelijen Berita untuk Suteki Technology, perusahaan EdTech penyedia "
            "SIAKAD Cloud, Pelaporan Neo Feeder PDDIKTI, Akreditasi Kampus (BAN-PT/LAM), SPMI, dan PMB Online di Indonesia.\n\n"
            "Tugas Anda untuk setiap artikel:\n"
            "1. 'skor' (skala 1-10): Relevansi isu terhadap bisnis Suteki Technology:\n"
            "   - Skor 8-10 (Tinggi/Prioritas): Isu SIAKAD, server kampus down saat KRS/PMB, regulasi baru PDDIKTI/Neo Feeder, akreditasi kampus, atau digitalisasi tata kelola perguruan tinggi.\n"
            "   - Skor 5-7 (Menengah): Isu pendidikan tinggi umum, UKT/biaya kuliah, SNPMB/PMB reguler, AI dalam pembelajaran, atau kegiatan universitas secara umum.\n"
            "   - Skor 1-4 (Rendah/Abaikan): Berita seremonial wisuda, kriminal/tawuran kampus, olahraga mahasiswa, atau berita sekolah dasar/menengah.\n"
            "2. 'alasan': 1 kalimat singkat alasan penilaian relevansi.\n"
            "3. 'ringkasan': 1 paragraf pendek (2-3 kalimat) yang menjelaskan intisari isu atau konteks berita agar tim redaksi langsung memahami isi pokoknya tanpa perlu membuka web aslinya.\n\n"
            "Daftar Artikel:\n" + "\n".join(prompt_items) + "\n\n"
            "Kembalikan HANYA format JSON valid berupa array of objects (tanpa markdown tambahan) dengan format persis:\n"
            "[\n"
            "  {\n"
            "    \"id\": 1,\n"
            "    \"skor\": 9,\n"
            "    \"alasan\": \"Membahas implementasi SIAKAD baru dan integrasi data\",\n"
            "    \"ringkasan\": \"Universitas Malikussaleh tengah mempersiapkan aplikasi SIAKAD versi baru guna meningkatkan efisiensi integrasi data akademik dan mutu layanan mahasiswa.\"\n"
            "  }\n"
            "]"
        )

        payload = {
            "contents": [{"parts": [{"text": prompt_text}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.2
            }
        }

        batch_success = False
        import time
        for model_name in candidate_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={clean_key}"
            try:
                resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=35)
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
                            # Jika cuplikan dari RSS masih kosong, gunakan ringkasan dari Gemini
                            if not target_art.get("cuplikan") or len(target_art["cuplikan"].strip()) < 30:
                                target_art["cuplikan"] = item.get("ringkasan", "")
                    print(f"[+] Berhasil menilai & merangkum {len(chunk)} artikel menggunakan {model_name}!")
                    batch_success = True
                    break
                elif resp.status_code in [503, 429]:
                    print(f"[WARN] Model {model_name} sedang sibuk (HTTP {resp.status_code}). Beralih ke model cadangan...")
                    time.sleep(1.5)
                    continue
                else:
                    print(f"[WARN] Model {model_name} mengembalikan HTTP {resp.status_code}: {resp.text[:100]}")
            except Exception as e:
                print(f"[WARN] Error saat request ke {model_name}: {e}")

        if not batch_success:
            print(f"[WARN] Seluruh model AI sedang padat untuk batch ini.")

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

def sync_to_google_sheets(articles, all_raw_feed_items=None):
    """Menyinkronkan artikel baru ke Google Sheets menggunakan Service Account."""
    if not HAS_GSPREAD:
        print("[!] Library 'gspread' atau 'google-auth' tidak terpasang. Mode Dry-Run aktif.")
        return False

    if all_raw_feed_items is None:
        all_raw_feed_items = []

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

        # Ambil baris pertama dan seluruh baris di sheet
        first_row = ws.row_values(1)
        all_rows = ws.get_all_values()

        # AUTO-MIGRATION: Jika sheet masih menggunakan format lama (< 12 kolom)
        if first_row and len(first_row) < len(HEADER_COLUMNS):
            print(f"[*] Terdeteksi skema tabel lama ({len(first_row)} kolom). Melakukan migrasi cerdas ke skema 12 kolom...")
            migrated_rows = []
            today_str = datetime.now().strftime("%Y-%m-%d")
            for r in all_rows[1:]:
                tgl_input = r[0].strip() if len(r) > 0 else today_str
                sumber = r[1].strip() if len(r) > 1 else ""
                judul = r[2].strip() if len(r) > 2 else ""
                url = r[3].strip() if len(r) > 3 else ""
                kata_kunci = r[4].strip() if len(r) > 4 else ""
                skor_awal = r[5].strip() if len(r) > 5 else ""
                catatan_awal = r[6].strip() if len(r) > 6 else ""
                skor_final = r[7].strip() if len(r) > 7 else ""
                rekomendasi = r[8].strip() if len(r) > 8 else ""
                status = r[9].strip() if len(r) > 9 else "Antrean"

                migrated_rows.append([
                    tgl_input,       # A: Tanggal Terbit
                    tgl_input,       # B: Tanggal Crawl
                    sumber,          # C: Sumber Media
                    judul,           # D: Judul Berita
                    "",              # E: Cuplikan Berita
                    url,             # F: URL Berita
                    kata_kunci,      # G: Kata Kunci Terdeteksi
                    skor_awal,       # H: Skor Awal Bot
                    catatan_awal,    # I: Catatan Awal Bot
                    skor_final,      # J: Skor Final Editorial
                    rekomendasi,     # K: Rekomendasi Angle Suteki
                    status           # L: Status Tindak Lanjut
                ])

            print(f"[*] Menulis ulang {len(migrated_rows)} baris data ke struktur 12 kolom...")
            ws.clear()
            ws.update(values=[HEADER_COLUMNS] + migrated_rows, range_name="A1")
            print("[OK] Migrasi skema 12 kolom sukses!")
            all_rows = ws.get_all_values()
        elif not first_row or len(first_row) < len(HEADER_COLUMNS) or first_row[0] != HEADER_COLUMNS[0] or first_row[4] != HEADER_COLUMNS[4]:
            print("[*] Menyesuaikan baris header tabel dengan format 12 kolom...")
            ws.update(values=[HEADER_COLUMNS], range_name="A1:L1")
            all_rows = ws.get_all_values()

        # Daftar URL yang sudah ada di Google Sheet (Kolom F / index 5)
        existing_urls = set()
        if len(all_rows) > 1:
            for r in all_rows[1:]:
                if len(r) > 5 and r[5].strip():
                    existing_urls.add(r[5].strip())
        print(f"[*] Ditemukan {len(existing_urls)} URL yang sudah ada di Google Sheet.")

        # ========================================================
        # RESTORASI & UPDATE TANGGAL TERBIT ASLI PADA BARIS SHEET
        # ========================================================
        # Buat pemetaan URL & Judul ke Tanggal Terbit asli dari seluruh feed
        feed_url_to_date = {}
        feed_title_to_date = {}
        feed_url_to_snippet = {}

        for itm in (all_raw_feed_items + articles):
            url_val = (itm.get("link") or itm.get("url") or "").strip()
            title_val = clean_title(itm.get("title") or itm.get("judul", "")).lower()
            date_val = (itm.get("date") or itm.get("tanggal_terbit") or "").strip()
            snippet_val = (itm.get("snippet") or itm.get("cuplikan") or "").strip()

            if url_val and date_val:
                feed_url_to_date[url_val] = date_val
            if title_val and date_val:
                feed_title_to_date[title_val] = date_val
            if url_val and snippet_val and len(snippet_val) > 30:
                feed_url_to_snippet[url_val] = snippet_val

        date_updates = []
        snippet_updates = []

        for row_idx, r_data in enumerate(all_rows[1:], start=2):
            r_pubdate = r_data[0].strip() if len(r_data) > 0 else ""
            r_crawldate = r_data[1].strip() if len(r_data) > 1 else ""
            r_title = clean_title(r_data[3]).lower() if len(r_data) > 3 else ""
            r_snippet = r_data[4].strip() if len(r_data) > 4 else ""
            r_url = r_data[5].strip() if len(r_data) > 5 else ""

            # Jika tanggal terbit masih sama dengan tanggal crawl atau belum ada jamnya
            needs_date_update = (not r_pubdate or r_pubdate == r_crawldate or len(r_pubdate) <= 10)

            if needs_date_update:
                resolved_date = None
                # 1. Cek exact match URL di feed
                if r_url in feed_url_to_date:
                    resolved_date = feed_url_to_date[r_url]
                # 2. Cek match judul berita di feed
                elif r_title in feed_title_to_date:
                    resolved_date = feed_title_to_date[r_title]
                # 3. Cek pola tanggal di URL asli
                else:
                    m = re.search(r'[-/](202[0-9])[-/]([0-1][0-9])[-/]([0-3][0-9])', r_url)
                    if m:
                        resolved_date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

                if resolved_date and resolved_date != r_pubdate:
                    date_updates.append({"range": f"A{row_idx}", "values": [[resolved_date]]})

            if not r_snippet and r_url in feed_url_to_snippet:
                snippet_updates.append({"range": f"E{row_idx}", "values": [[feed_url_to_snippet[r_url]]]})

        all_meta_updates = date_updates + snippet_updates
        if all_meta_updates:
            print(f"[*] Menyesuaikan {len(date_updates)} Tanggal Terbit asli dan {len(snippet_updates)} Cuplikan di Google Sheet...")
            for i in range(0, len(all_meta_updates), 100):
                chunk_upd = all_meta_updates[i:i + 100]
                try:
                    ws.batch_update(chunk_upd, value_input_option="USER_ENTERED")
                except Exception as e_feed:
                    for d in chunk_upd:
                        try:
                            ws.update(values=d["values"], range_name=d["range"])
                        except Exception:
                            pass
            print(f"[OK] Berhasil memperbarui {len(all_meta_updates)} sel metadata di Google Sheet!")

        # ========================================================
        # PENAMBAHAN ARTIKEL YANG BENAR-BENAR BARU
        # ========================================================
        truly_new_articles = [art for art in articles if art["url"] not in existing_urls]
        print(f"[+] Ditemukan {len(truly_new_articles)} artikel yang benar-benar baru.")

        if truly_new_articles:
            # Jalankan AI Scoring Awal (Gemini) HANYA untuk artikel yang baru!
            scored_articles = score_articles_with_gemini(truly_new_articles, gemini_api_key)

            new_rows = []
            for art in scored_articles:
                new_rows.append([
                    art["tanggal_terbit"],
                    art["tanggal_crawl"],
                    art["sumber"],
                    art["judul"],
                    art.get("cuplikan", ""),
                    art["url"],
                    art["kata_kunci"],
                    art.get("skor_awal", ""),
                    art.get("alasan_awal", ""),
                    "",  # Skor Final Editorial (dikosongkan untuk ChatGPT)
                    "",  # Rekomendasi Angle Suteki (dikosongkan untuk ChatGPT)
                    "Antrean"  # Status Tindak Lanjut awal
                ])
                existing_urls.add(art["url"])

            print(f"[+] Menyimpan {len(new_rows)} artikel baru lengkap dengan Ringkasan & Scoring Awal...")
            ws.append_rows(new_rows, value_input_option="USER_ENTERED")
            print("[OK] Sinkronisasi artikel baru ke Google Sheets berhasil!")
        else:
            print("[INFO] Tidak ada artikel baru yang perlu ditambahkan (semua URL sudah tercatat).")

        # ========================================================
        # FITUR OPTION A: Full Backfill Scoring & Cuplikan untuk baris tanpa Skor
        # ========================================================
        try:
            if gemini_api_key and gemini_api_key.strip():
                latest_rows = ws.get_all_values()
                
                unscored_items = []
                for row_idx, r_data in enumerate(latest_rows[1:], start=2):
                    score_val = r_data[7].strip() if len(r_data) > 7 else ""
                    if not score_val:
                        unscored_items.append({
                            "row_num": row_idx,
                            "sumber": r_data[2].strip() if len(r_data) > 2 else "",
                            "judul": r_data[3].strip() if len(r_data) > 3 else "",
                            "cuplikan": r_data[4].strip() if len(r_data) > 4 else "",
                            "url": r_data[5].strip() if len(r_data) > 5 else "",
                            "kata_kunci": r_data[6].strip() if len(r_data) > 6 else ""
                        })

                if unscored_items:
                    total_unscored = len(unscored_items)
                    chunk_size = 25
                    total_batches = (total_unscored + chunk_size - 1) // chunk_size
                    print(f"[*] Menjalankan Full Backfill (Option A) untuk {total_unscored} artikel...")
                    print(f"[*] Dibagi menjadi {total_batches} batch (@ {chunk_size} artikel/batch) dengan jeda aman...")
                    
                    import time
                    total_updated = 0
                    for b_idx in range(0, total_unscored, chunk_size):
                        chunk = unscored_items[b_idx:b_idx + chunk_size]
                        batch_num = (b_idx // chunk_size) + 1
                        print(f"[*] [Batch {batch_num}/{total_batches}] Menilai & merangkum {len(chunk)} artikel...")
                        
                        scored_chunk = score_articles_with_gemini(chunk, gemini_api_key)
                        
                        batch_updates = []
                        for itm in scored_chunk:
                            rn = itm["row_num"]
                            if itm.get("cuplikan"):
                                batch_updates.append({
                                    "range": f"E{rn}",
                                    "values": [[str(itm.get("cuplikan", ""))]]
                                })
                            if itm.get("skor_awal"):
                                batch_updates.append({
                                    "range": f"H{rn}:I{rn}",
                                    "values": [[str(itm.get("skor_awal", "")), str(itm.get("alasan_awal", ""))]]
                                })
                        
                        if batch_updates:
                            try:
                                ws.batch_update(batch_updates, value_input_option="USER_ENTERED")
                            except Exception as e_batch:
                                print(f"[WARN] ws.batch_update gagal ({e_batch}), menggunakan fallback baris per baris...")
                                for upd in batch_updates:
                                    try:
                                        ws.update(values=upd["values"], range_name=upd["range"])
                                    except Exception:
                                        pass
                            total_updated += len([x for x in batch_updates if x["range"].startswith("H")])
                            print(f"[OK] [Batch {batch_num}/{total_batches}] Berhasil menyimpan skor & cuplikan ke Google Sheet.")
                            
                        # Beri jeda 2 detik antar batch agar tetap aman dalam batas 15 RPM
                        if b_idx + chunk_size < total_unscored:
                            time.sleep(2)
                            
                    print(f"[SUKSES] Full Backfill Selesai! Sebanyak {total_updated} dari {total_unscored} baris telah berhasil dinilai.")
                else:
                    print("[INFO] Seluruh baris di Google Sheet sudah memiliki skor awal (tidak ada antrean backfill).")
        except Exception as e:
            print(f"[WARN] Melewati auto-backfill skor: {e}")
            traceback.print_exc()

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

    articles, all_raw_feed_items = collect_all_articles()

    # Coba sinkronisasi ke Google Sheets
    synced = sync_to_google_sheets(articles, all_raw_feed_items)

    # Jika belum tersambung ke Google Sheets (Dry-run), simpan pratinjau lokal
    if not synced:
        preview_file = "preview_radar.json"
        with open(preview_file, "w", encoding="utf-8") as f:
            json.dump(articles, f, indent=2, ensure_ascii=False)
        print(f"[OK] Hasil penarikan disimpan ke pratinjau lokal: '{preview_file}'")
        print(f"[i] Contoh 3 artikel pertama:")
        for idx, item in enumerate(articles[:3], 1):
            print(f"    {idx}. [{item['sumber']}] {item['judul']}")
            print(f"       Tanggal Terbit: {item['tanggal_terbit']} | Crawl: {item['tanggal_crawl']}")
            if item.get("cuplikan"):
                print(f"       Cuplikan: {item['cuplikan'][:120]}...")
            print(f"       Tag: {item['kata_kunci']}")
            print(f"       URL: {item['url']}")

if __name__ == "__main__":
    main()
