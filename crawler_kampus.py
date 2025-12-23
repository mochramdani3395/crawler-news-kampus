import trafilatura
from trafilatura.spider import focused_crawler
import json
import os
import requests
import re
import hashlib
from datetime import datetime
from urllib.parse import urlparse

# --- KONFIGURASI ---
TELEGRAM_TOKEN = "GANTI_DENGAN_TOKEN_BOT_ANDA"
TELEGRAM_CHAT_ID = "GANTI_DENGAN_CHAT_ID_ANDA"
DB_FILE = "database_artikel.json"
BASE_ARCHIVE_FOLDER = "arsip_artikel"

def slugify(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text).strip('-')
    return text[:60]

def get_smart_title(data, link):
    judul = data.get('title')
    if not judul or judul == "Tanpa Judul" or len(judul) < 5:
        path_segments = [s for s in link.split('/') if s]
        if path_segments:
            judul = path_segments[-1].replace('-', ' ').replace('.html', '').title()
    return judul if judul else "Artikel Tanpa Judul"

def save_as_markdown(judul, isi, tanggal, penulis, link, image_url, nama_kampus):
    """Menyimpan file ke dalam sub-folder nama kampus"""
    clean_title = slugify(judul)
    date_prefix = datetime.now().strftime('%Y%m%d')
    unique_id = hashlib.md5(link.encode()).hexdigest()[:6]
    
    # 1. Tentukan lokasi folder (arsip_artikel/nama-kampus)
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
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML", "disable_web_page_preview": True}
    try: requests.post(url, data=payload)
    except: pass

def jalankan_crawler(daftar_web):
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f: database = json.load(f)
    else:
        database = []

    existing_urls = [item['link'] for item in database]
    notif_list = []

    for nama_kampus, domain in daftar_web.items():
        print(f"Mengecek {nama_kampus}: {domain}")
        try:
            links, _ = focused_crawler(domain, max_seen_urls=10)
            if links:
                for link in links:
                    if link not in existing_urls:
                        downloaded = trafilatura.fetch_url(link)
                        result = trafilatura.extract(downloaded, output_format='json', include_comments=False)
                        
                        if result:
                            data = json.loads(result)
                            judul = get_smart_title(data, link)
                            image_url = data.get('image')
                            
                            # Simpan dengan parameter nama_kampus
                            rel_path = save_as_markdown(
                                judul, data.get('text', ''), 
                                data.get('date', 'N/A'), 
                                data.get('author', 'Humas'), 
                                link, image_url, nama_kampus
                            )
                            
                            entry = {
                                "kampus": nama_kampus,
                                "judul": judul, 
                                "link": link, 
                                "file_arsip": f"{BASE_ARCHIVE_FOLDER}/{rel_path}",
                                "waktu_crawl": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            }
                            database.append(entry)
                            notif_list.append(f"🔹 [{nama_kampus}] {judul}")
                            existing_urls.append(link)
        except Exception as e:
            print(f"Error pada {nama_kampus}: {e}")

    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(database, f, indent=4, ensure_ascii=False)

    if notif_list:
        msg = f"📰 <b>{len(notif_list)} Berita Kampus Baru!</b>\n\n"
        msg += "\n".join(notif_list[:15])
        send_telegram(msg)

if __name__ == "__main__":
    # FORMAT BARU: "Nama Kampus": "URL Berita"
    dict_universitas = {
        "UPB": "https://upb.ac.id/berita",
        "UNNUR": "https://unnur.ac.id/berita",
        "UTS Makassar": "https://utsmakassar.ac.id/berita"
    }
    jalankan_crawler(dict_universitas)
