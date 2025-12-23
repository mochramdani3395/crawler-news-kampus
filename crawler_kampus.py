import trafilatura
from trafilatura.spider import focused_crawler # Impor eksplisit agar tidak error
import json, os, requests, re, hashlib, time, random
from datetime import datetime

# --- KONFIGURASI ---
def load_config():
    with open("config.json", "r") as f:
        return json.load(f)

CONFIG = load_config()
TELEGRAM_TOKEN = CONFIG["telegram_token"]
TELEGRAM_CHAT_ID = CONFIG["telegram_chat_id"]
TARGET_KAMPUS = CONFIG["target_kampus"]
MAX_LINKS = CONFIG.get("max_links_per_run", 3)
DELAY_MIN = CONFIG.get("delay_min", 15)
DELAY_MAX = CONFIG.get("delay_max", 12)

DB_FILE = "database_artikel.json"
BASE_ARCHIVE_FOLDER = "arsip_artikel"
REPO_PATH = os.getenv('GITHUB_REPOSITORY', 'mochramdani3395/crawler-news-kampus')
REPO_URL = f"https://github.com/{REPO_PATH}/blob/main"

if not os.path.exists(BASE_ARCHIVE_FOLDER):
    os.makedirs(BASE_ARCHIVE_FOLDER)

def slugify(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text).strip('-')
    return text[:60]

def get_smart_title(data, link):
    """Logika Anda: Mengambil judul dari metadata atau URL"""
    judul = data.get('title')
    if not judul or judul == "Berita Baru" or len(judul) < 10:
        path_segments = [s for s in link.split('/') if s]
        if path_segments:
            # Mengambil segment terakhir URL sebagai judul cadangan
            judul = path_segments[-1].replace('-', ' ').replace('.html', '').title()
    return judul if judul else "Artikel Tanpa Judul"

def save_as_markdown(judul, isi, tanggal, penulis, link, image_url, nama_kampus):
    clean_title = slugify(judul)
    date_prefix = datetime.now().strftime('%Y%m%d')
    unique_id = hashlib.md5(link.encode()).hexdigest()[:6]
    
    folder_path = os.path.join(BASE_ARCHIVE_FOLDER, slugify(nama_kampus))
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    
    filename = f"{date_prefix}-{clean_title}-{unique_id}.md"
    filepath = os.path.join(folder_path, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# {judul}\n\n")
        if image_url:
            f.write(f"![Gambar Utama]({image_url})\n\n")
        f.write(f"- **Kampus:** {nama_kampus}\n")
        f.write(f"- **Sumber:** {link}\n")
        f.write(f"- **Penulis:** {penulis}\n")
        f.write(f"- **Tanggal Posting:** {tanggal}\n")
        f.write(f"- **Waktu Crawl:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"---\n\n")
        f.write(isi if isi else "Konten teks tidak berhasil diekstrak.")
        
    return f"{slugify(nama_kampus)}/{filename}"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML", "disable_web_page_preview": False}
    try: requests.post(url, data=payload, timeout=20)
    except: pass

def jalankan_crawler():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            database = json.load(f)
    else:
        database = []

    existing_urls = {item['link'] for item in database}
    notif_list = []

    # SHUFFLING & BATCHING
    item_kampus = list(TARGET_KAMPUS.items())
    random.shuffle(item_kampus)

    for nama_kampus, domain in item_kampus:
        print(f"Mengecek {nama_kampus}: {domain}")
        try:
            # Mencari link di halaman utama berita
            links, _ = focused_crawler(domain, max_seen_urls=15)
            
            # DISCOVERY ONLY: Filter link yang benar-benar artikel baru
            # l.rstrip('/') != domain.rstrip('/') memastikan halaman daftar tidak di-crawl sebagai artikel
            article_links = [l for l in links if l not in existing_urls and l.rstrip('/') != domain.rstrip('/')]
            
            count = 0
            for link in article_links:
                if count >= MAX_LINKS: break
                
                # BATCHING: Jeda antar artikel
                time.sleep(random.randint(DELAY_MIN, DELAY_MAX))
                
                downloaded = trafilatura.fetch_url(link)
                if not downloaded: continue
                
                result = trafilatura.extract(downloaded, output_format='json', include_comments=False)
                if result:
                    data = json.loads(result)
                    judul = get_smart_title(data, link)
                    
                    # Simpan file
                    rel_path = save_as_markdown(
                        judul, 
                        data.get('text', ''), 
                        data.get('date', 'N/A'), 
                        data.get('author', 'Humas'), 
                        link, 
                        data.get('image'), 
                        nama_kampus
                    )

                    entry = {
                        "kampus": nama_kampus,
                        "judul": judul,
                        "link": link,
                        "file_arsip": f"{BASE_ARCHIVE_FOLDER}/{rel_path}",
                        "waktu_crawl": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                    database.append(entry)
                    
                    github_link = f"{REPO_URL}/{BASE_ARCHIVE_FOLDER}/{rel_path}"
                    notif_list.append(f"🔹 [{nama_kampus}] <a href='{github_link}'>{judul}</a>")
                    existing_urls.add(link)
                    print(f"  > Berhasil: {judul}")
                    count += 1
                    
        except Exception as e:
            print(f"Error pada {nama_kampus}: {e}")

    # Simpan DB
    database.sort(key=lambda x: x['waktu_crawl'], reverse=True)
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(database, f, indent=4, ensure_ascii=False)

    # Kirim Notifikasi
    if notif_list:
        chunk_size = 10
        for i in range(0, len(notif_list), chunk_size):
            msg = f"📰 <b>{len(notif_list)} Berita Kampus Baru!</b>\n\n"
            msg += "\n".join(notif_list[i:i+chunk_size])
            send_telegram(msg)
            time.sleep(2)
    else:
        print("Selesai. Tidak ada berita baru.")

if __name__ == "__main__":
    jalankan_crawler()
