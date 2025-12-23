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
MAX_LINKS = 15 # Ambil 3 artikel terbaru saja per run
DELAY = 5     # Jeda 5 detik antar klik agar aman

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
        f.write(f"- **Sumber:** {link}\n")
        f.write(f"- **Waktu Crawl:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"---\n\n{isi}")
    return f"{slugify(nama_kampus)}/{filename}"

def jalankan_crawler():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f: database = json.load(f)
    else: database = []

    existing_urls = {item['link'] for item in database}
    notif_list = []
    
    # Acak daftar kampus
    item_kampus = list(TARGET_KAMPUS.items())
    random.shuffle(item_kampus)

    for nama_kampus, domain in item_kampus:
        print(f"Mencari artikel di: {nama_kampus}")
        try:
            # Cari semua link di halaman berita
            links, _ = focused_crawler(domain, max_seen_urls=15)
            
            # FILTER: Hanya ambil link yang BUKAN halaman utama berita itu sendiri
            # Dan link harus lebih panjang (ciri khas link artikel detail)
            article_links = [
                l for l in links 
                if l.strip('/') != domain.strip('/') 
                and len(l) > len(domain) + 5
                and l not in existing_urls
            ]

            processed_count = 0
            for link in article_links:
                if processed_count >= MAX_LINKS: break
                
                print(f"  > Klik masuk ke: {link}")
                time.sleep(DELAY) # Jeda agar tidak dianggap DDoS
                
                downloaded = trafilatura.fetch_url(link)
                if not downloaded: continue
                
                result = trafilatura.extract(downloaded, output_format='json')
                if result:
                    data = json.loads(result)
                    judul = data.get('title')
                    isi = data.get('text')
                    
                    # Validasi: Jika judul pendek atau isi cuma sedikit, abaikan
                    if not judul or len(judul) < 10 or not isi or len(isi) < 100:
                        continue

                    rel_path = save_as_markdown(judul, isi, link, data.get('image'), nama_kampus)
                    
                    database.append({
                        "kampus": nama_kampus,
                        "judul": judul,
                        "link": link,
                        "waktu_crawl": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    })
                    notif_list.append(f"🔹 [{nama_kampus}] {judul}")
                    existing_urls.add(link)
                    processed_count += 1

        except Exception as e:
            print(f"Error pada {nama_kampus}: {e}")

    # Simpan database
    database.sort(key=lambda x: x['waktu_crawl'], reverse=True)
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(database, f, indent=4, ensure_ascii=False)

if __name__ == "__main__":
    jalankan_crawler()
