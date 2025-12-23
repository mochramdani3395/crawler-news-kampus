import trafilatura
from trafilatura.spider import focused_crawler
import json, os, requests, re, hashlib, time
from datetime import datetime

# --- LOAD CONFIG ---
def load_config():
    with open("config.json", "r") as f:
        return json.load(f)

CONFIG = load_config()
TELEGRAM_TOKEN = CONFIG["telegram_token"]
TELEGRAM_CHAT_ID = CONFIG["telegram_chat_id"]
TARGET_KAMPUS = CONFIG["target_kampus"]
MAX_LINKS = CONFIG.get("max_links_per_run", 10)
DELAY = CONFIG.get("delay_seconds", 2)

DB_FILE = "database_artikel.json"
BASE_ARCHIVE_FOLDER = "arsip_artikel"

def slugify(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text).strip('-')
    return text[:60]

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
        f.write(f"- **Kampus:** {nama_kampus}\n- **Sumber:** {link}\n- **Waktu Crawl:** {datetime.now()}\n\n---\n\n{isi}")
    return f"{slugify(nama_kampus)}/{filename}"

# Tambahkan ini di bagian atas untuk memudahkan pembuatan link
REPO_URL = "https://github.com/USERNAME_ANDA/crawler-news-kampus/blob/main"

# Modifikasi bagian notifikasi di dalam loop jalankan_crawler
notif_list.append(f"🔹 [{nama_kampus}] <a href='{REPO_URL}/{BASE_ARCHIVE_FOLDER}/{rel_path}'>{judul}</a>")

# Pastikan fungsi send_telegram memiliki parse_mode HTML
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID, 
        "text": message, 
        "parse_mode": "HTML", 
        "disable_web_page_preview": False # Ubah jadi False agar preview link muncul
    }
    requests.post(url, data=payload, timeout=10)

def jalankan_crawler():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f: database = json.load(f)
    else: database = []

    existing_urls = [item['link'] for item in database]
    notif_list = []

    for nama_kampus, domain in TARGET_KAMPUS.items():
        print(f"Mengecek {nama_kampus}...")
        try:
            # Batasi pencarian link agar tidak overload
            links, _ = focused_crawler(domain, max_seen_urls=MAX_LINKS)
            if links:
                for link in links:
                    if link not in existing_urls:
                        time.sleep(DELAY) # JEDA ANTAR REQUEST
                        downloaded = trafilatura.fetch_url(link)
                        if not downloaded: continue
                        
                        result = trafilatura.extract(downloaded, output_format='json')
                        if result:
                            data = json.loads(result)
                            judul = data.get('title') or link.split('/')[-1]
                            img = data.get('image')
                            
                            rel_path = save_as_markdown(judul, data.get('text', ''), 'N/A', 'Humas', link, img, nama_kampus)
                            
                            database.append({
                                "kampus": nama_kampus,
                                "judul": judul,
                                "link": link,
                                "waktu_crawl": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                "file_arsip": f"{BASE_ARCHIVE_FOLDER}/{rel_path}"
                            })
                            notif_list.append(f"🔹 [{nama_kampus}] {judul}")
                            existing_urls.append(link)
        except Exception as e: print(f"Skip {nama_kampus} karena error: {e}")

    # SORTING: Berita terbaru (berdasarkan waktu crawl) di atas
    database.sort(key=lambda x: x['waktu_crawl'], reverse=True)

    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(database, f, indent=4, ensure_ascii=False)

    if notif_list:
        send_telegram(f"📰 <b>{len(notif_list)} Berita Baru!</b>\n\n" + "\n".join(notif_list[:15]))

if __name__ == "__main__":
    jalankan_crawler()
