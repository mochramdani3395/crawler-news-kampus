import trafilatura
from trafilatura.spider import focused_crawler
import json, os, requests, re, hashlib, time, random
from datetime import datetime

# --- LOAD CONFIG ---
def load_config():
    with open("config.json", "r") as f:
        return json.load(f)

CONFIG = load_config()
TELEGRAM_TOKEN = CONFIG["telegram_token"]
TELEGRAM_CHAT_ID = CONFIG["telegram_chat_id"]
TARGET_KAMPUS = CONFIG["target_kampus"]
MAX_LINKS = CONFIG.get("max_links_per_run", 3)
DELAY_MIN = CONFIG.get("delay_min", 5)
DELAY_MAX = CONFIG.get("delay_max", 12)

DB_FILE = "database_artikel.json"
BASE_ARCHIVE_FOLDER = "arsip_artikel"
REPO_PATH = os.getenv('GITHUB_REPOSITORY', 'mochramdani3395/crawler-news-kampus')
REPO_URL = f"https://github.com/{REPO_PATH}/blob/main"

# Header Penyamaran Browser
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
    'Referer': 'https://www.google.com/'
}

def slugify(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text).strip('-')
    return text[:60]

def get_smart_title(data, link):
    judul = data.get('title')
    if not judul or "berita" in judul.lower() or len(judul) < 10:
        path_segments = [s for s in link.split('/') if s]
        if path_segments:
            judul = path_segments[-1].replace('-', ' ').replace('.html', '').title()
    return judul if judul else "Artikel Tanpa Judul"

def fetch_tangguh(url):
    """Mengambil konten dengan requests jika trafilatura diblokir (Error 403)"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
        if response.status_code == 200:
            return response.text
    except Exception as e:
        print(f"  [!] Gagal fetch {url}: {e}")
    return None

def save_as_markdown(judul, isi, tanggal, penulis, link, image_url, nama_kampus):
    clean_title = slugify(judul)
    date_prefix = datetime.now().strftime('%Y%m%d')
    unique_id = hashlib.md5(link.encode()).hexdigest()[:6]
    
    folder_path = os.path.join(BASE_ARCHIVE_FOLDER, slugify(nama_kampus))
    if not os.path.exists(folder_path): os.makedirs(folder_path)
    
    filename = f"{date_prefix}-{clean_title}-{unique_id}.md"
    filepath = os.path.join(folder_path, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# {judul}\n\n")
        if image_url: f.write(f"![Gambar Utama]({image_url})\n\n")
        f.write(f"- **Kampus:** {nama_kampus}\n")
        f.write(f"- **Sumber:** {link}\n")
        f.write(f"- **Penulis:** {penulis}\n")
        f.write(f"- **Tanggal Posting:** {tanggal}\n")
        f.write(f"- **Waktu Crawl:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"---\n\n{isi}")
    return f"{slugify(nama_kampus)}/{filename}"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try: requests.post(url, data=payload, timeout=20)
    except: pass

def jalankan_crawler():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f: database = json.load(f)
    else: database = []

    existing_urls = {item['link'] for item in database}
    notif_list = []
    item_kampus = list(TARGET_KAMPUS.items())
    random.shuffle(item_kampus)

    for nama_kampus, domain in item_kampus:
        print(f"Memproses {nama_kampus}...")
        html_index = fetch_tangguh(domain)
        if not html_index: continue

        # Ekstrak link dari halaman index
        links = trafilatura.spider.utils.extract_links(html_index, url=domain)
        article_links = [l for l in links if l not in existing_urls and len(l) > len(domain) + 3]

        count = 0
        for link in article_links:
            if count >= MAX_LINKS: break
            time.sleep(random.randint(DELAY_MIN, DELAY_MAX))
            
            html_article = fetch_tangguh(link)
            if not html_article: continue
            
            result = trafilatura.extract(html_article, output_format='json')
            if result:
                data = json.loads(result)
                judul = get_smart_title(data, link)
                isi = data.get('text', '')
                if len(isi) < 200: continue

                rel_path = save_as_markdown(judul, isi, data.get('date', 'N/A'), data.get('author', 'Humas'), link, data.get('image'), nama_kampus)
                
                database.append({"kampus": nama_kampus, "judul": judul, "link": link, "waktu_crawl": datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
                github_link = f"{REPO_URL}/{BASE_ARCHIVE_FOLDER}/{rel_path}"
                notif_list.append(f"🔹 [{nama_kampus}] <a href='{github_link}'>{judul}</a>")
                existing_urls.add(link)
                count += 1

    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(database, f, indent=4, ensure_ascii=False)

    if notif_list:
        # Perbaikan baris yang menyebabkan SyntaxError
        header_msg = f"<b>{len(notif_list)} Berita Kampus Baru!</b>\n\n"
        body_msg = "\n".join(notif_list[:15])
        send_telegram(header_msg + body_msg)

if __name__ == "__main__":
    jalankan_crawler()
