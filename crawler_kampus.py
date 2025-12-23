import trafilatura
from trafilatura.sitemaps import sitemap_search
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
MAX_LINKS = CONFIG.get("max_links_per_run", 5)
DELAY_MIN = CONFIG.get("delay_min", 5)
DELAY_MAX = CONFIG.get("delay_max", 12)

# Deteksi otomatis path repository untuk link Telegram
REPO_PATH = os.getenv('GITHUB_REPOSITORY', 'mochramdani3395/crawler-news-kampus')
REPO_URL = f"https://github.com/{REPO_PATH}/blob/main"
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
        if image_url and image_url.startswith("http"):
            f.write(f"![Gambar Utama]({image_url})\n\n")
        f.write(f"- **Kampus:** {nama_kampus}\n")
        f.write(f"- **Sumber:** {link}\n")
        f.write(f"- **Waktu Crawl:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"---\n\n")
        f.write(isi if isi else "Konten teks tidak berhasil diekstrak.")
    return f"{slugify(nama_kampus)}/{filename}"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML", "disable_web_page_preview": False}
    try: requests.post(url, data=payload, timeout=20)
    except: pass

def get_links(url):
    """Mencoba mencari link lewat sitemap dahulu, lalu fallback ke crawl biasa"""
    # 1. Coba lewat sitemap (lebih akurat untuk berita terbaru)
    links = sitemap_search(url)
    if not links:
        # 2. Jika sitemap gagal, gunakan crawler standar
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            links = trafilatura.spider.utils.extract_links(downloaded, url=url, external=False)
    return list(set(links)) if links else []

def jalankan_crawler():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f: database = json.load(f)
    else: database = []

    existing_urls = {item['link'] for item in database}
    notif_list = []

    # SHUFFLING: Acak urutan kampus
    item_kampus = list(TARGET_KAMPUS.items())
    random.shuffle(item_kampus)

    for nama_kampus, domain in item_kampus:
        print(f"Siklus: Mengecek {nama_kampus}...")
        try:
            links = get_links(domain)
            
            # Filter hanya link yang belum pernah di-crawl
            new_links = [l for l in links if l not in existing_urls]
            
            # Ambil hanya sebanyak MAX_LINKS terbaru
            for link in new_links[:MAX_LINKS]:
                time.sleep(random.randint(DELAY_MIN, DELAY_MAX))
                
                downloaded = trafilatura.fetch_url(link)
                if not downloaded: continue
                
                result = trafilatura.extract(downloaded, output_format='json', include_comments=False)
                if result:
                    data = json.loads(result)
                    judul = data.get('title') or "Berita Baru"
                    img = data.get('image')
                    
                    rel_path = save_as_markdown(judul, data.get('text', ''), 'N/A', 'Humas', link, img, nama_kampus)
                    
                    database.append({
                        "kampus": nama_kampus,
                        "judul": judul,
                        "link": link,
                        "waktu_crawl": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        "file_arsip": f"{BASE_ARCHIVE_FOLDER}/{rel_path}"
                    })
                    
                    github_link = f"{REPO_URL}/{BASE_ARCHIVE_FOLDER}/{rel_path}"
                    notif_list.append(f"🔹 [{nama_kampus}] <a href='{github_link}'>{judul}</a>")
                    existing_urls.add(link)
        except Exception as e:
            print(f"Gagal memproses {nama_kampus}: {e}")

    # Sorting: Urutkan data berdasarkan waktu crawl terbaru
    database.sort(key=lambda x: x['waktu_crawl'], reverse=True)

    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(database, f, indent=4, ensure_ascii=False)

    if notif_list:
        chunk_size = 10
        for i in range(0, len(notif_list), chunk_size):
            msg = f"📰 <b>Update Berita Kampus ({i//chunk_size + 1})</b>\n\n" + "\n".join(notif_list[i:i+chunk_size])
            send_telegram(msg)
            time.sleep(3)

if __name__ == "__main__":
    jalankan_crawler()
