import trafilatura
# Import spesifik untuk menghindari error 'no attribute spider'
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
MAX_LINKS = CONFIG.get("max_links_per_run", 3) # Kecil saja agar aman
DELAY_MIN = CONFIG.get("delay_min", 5)
DELAY_MAX = CONFIG.get("delay_max", 10)

REPO_PATH = os.getenv('GITHUB_REPOSITORY', 'mochramdani3395/crawler-news-kampus')
REPO_URL = f"https://github.com/{REPO_PATH}/blob/main"
DB_FILE = "database_artikel.json"
BASE_ARCHIVE_FOLDER = "arsip_artikel"

def slugify(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text).strip('-')
    return text[:60]

def save_as_markdown(judul, isi, link, image_url, nama_kampus):
    clean_title = slugify(judul)
    date_prefix = datetime.now().strftime('%Y%m%d')
    unique_id = hashlib.md5(link.encode()).hexdigest()[:6]
    
    folder_path = os.path.join(BASE_ARCHIVE_FOLDER, slugify(nama_kampus))
    if not os.path.exists(folder_path): os.makedirs(folder_path)
    
    filename = f"{date_prefix}-{clean_title}-{unique_id}.md"
    filepath = os.path.join(folder_path, filename)
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# {judul}\n\n")
        if image_url: f.write(f"![Gambar]({image_url})\n\n")
        f.write(f"- **Kampus:** {nama_kampus}\n")
        f.write(f"- **Sumber Asli:** {link}\n")
        f.write(f"- **Waktu Crawl:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"---\n\n{isi}")
    return f"{slugify(nama_kampus)}/{filename}"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML", "disable_web_page_preview": False}
    try: requests.post(url, data=payload, timeout=20)
    except: pass

def jalankan_crawler():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f: database = json.load(f)
    else: database = []

    existing_urls = {item['link'] for item in database}
    notif_list = []
    
    # Shuffle kampus agar acak
    item_kampus = list(TARGET_KAMPUS.items())
    random.shuffle(item_kampus)

    for nama_kampus, domain in item_kampus:
        print(f"Memproses: {nama_kampus}")
        try:
            # Menggunakan focused_crawler dengan benar
            links, _ = focused_crawler(domain, max_seen_urls=10)
            
            # Filter hanya link yang benar-benar artikel (bukan halaman /berita/ itu sendiri)
            new_links = [l for l in links if l not in existing_urls and l.rstrip('/') != domain.rstrip('/')]
            
            for link in new_links[:MAX_LINKS]:
                time.sleep(random.randint(DELAY_MIN, DELAY_MAX))
                downloaded = trafilatura.fetch_url(link)
                if not downloaded: continue
                
                result = trafilatura.extract(downloaded, output_format='json')
                if result:
                    data = json.loads(result)
                    judul = data.get('title')
                    # Jika judul gagal diambil, lewati atau cari alternatif
                    if not judul or len(judul) < 10: continue 

                    rel_path = save_as_markdown(judul, data.get('text', ''), link, data.get('image'), nama_kampus)
                    
                    entry = {
                        "kampus": nama_kampus,
                        "judul": judul,
                        "link": link,
                        "waktu_crawl": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        "file_arsip": f"{BASE_ARCHIVE_FOLDER}/{rel_path}"
                    }
                    database.append(entry)
                    notif_list.append(f"🔹 [{nama_kampus}] <a href='{REPO_URL}/{BASE_ARCHIVE_FOLDER}/{rel_path}'>{judul}</a>")
                    existing_urls.add(link)

        except Exception as e:
            print(f"Error di {nama_kampus}: {e}")

    database.sort(key=lambda x: x['waktu_crawl'], reverse=True)
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(database, f, indent=4, ensure_ascii=False)

    if notif_list:
        msg = f"📰 <b>{len(notif_list)} Berita Baru!</b>\n\n" + "\n".join(notif_list[:15])
        send_telegram(msg)

if __name__ == "__main__":
    jalankan_crawler()
