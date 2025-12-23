import trafilatura
from trafilatura.spider import focused_crawler
import json
import os
import requests
import re
import hashlib
from datetime import datetime

# --- KONFIGURASI ---
# Pastikan Token dan Chat ID tetap terisi dengan benar
TELEGRAM_TOKEN = "GANTI_DENGAN_TOKEN_BOT_ANDA"
TELEGRAM_CHAT_ID = "GANTI_DENGAN_CHAT_ID_ANDA"
DB_FILE = "database_artikel.json"
ARCHIVE_FOLDER = "arsip_artikel"

if not os.path.exists(ARCHIVE_FOLDER):
    os.makedirs(ARCHIVE_FOLDER)

def slugify(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text).strip('-')
    return text[:60]

def get_smart_title(data, link):
    """Strategi pintar untuk mengambil judul artikel"""
    # 1. Coba ambil dari hasil ekstrak utama
    judul = data.get('title')
    
    # 2. Jika gagal atau judul terlalu pendek (biasanya noise), coba ambil dari metadata alternatif
    if not judul or judul == "Tanpa Judul" or len(judul) < 5:
        # Ambil bagian terakhir dari URL, ganti '-' jadi spasi, dan jadikan format Judul
        path_segments = [s for s in link.split('/') if s]
        if path_segments:
            judul = path_segments[-1].replace('-', ' ').replace('.html', '').title()
            
    return judul if judul else "Artikel Tanpa Judul"

def save_as_markdown(judul, isi, tanggal, penulis, link):
    clean_title = slugify(judul)
    date_prefix = datetime.now().strftime('%Y%m%d')
    
    # Tambahkan ID unik berdasarkan link agar file tidak tertimpa jika judul sama
    unique_id = hashlib.md5(link.encode()).hexdigest()[:6]
    filename = f"{date_prefix}-{clean_title}-{unique_id}.md"
    filepath = os.path.join(ARCHIVE_FOLDER, filename)
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# {judul}\n\n")
        f.write(f"- **Sumber:** {link}\n")
        f.write(f"- **Penulis:** {penulis}\n")
        f.write(f"- **Tanggal Posting:** {tanggal}\n")
        f.write(f"- **Waktu Crawl:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"---\n\n")
        f.write(isi if isi else "Konten tidak berhasil diekstrak.")
    return filename

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

    for domain in daftar_web:
        print(f"Mengecek: {domain}")
        try:
            links, _ = focused_crawler(domain, max_seen_urls=10)
            if links:
                for link in links:
                    if link not in existing_urls:
                        downloaded = trafilatura.fetch_url(link)
                        # Extract dengan deteksi bahasa otomatis agar lebih akurat
                        result = trafilatura.extract(downloaded, output_format='json', include_comments=False)
                        
                        if result:
                            data = json.loads(result)
                            
                            # MENGGUNAKAN FUNGSI PINTAR UNTUK JUDUL
                            judul = get_smart_title(data, link)
                            
                            nama_file = save_as_markdown(
                                judul, 
                                data.get('text', ''), 
                                data.get('date', 'N/A'), 
                                data.get('author', 'Humas'), 
                                link
                            )
                            
                            entry = {
                                "judul": judul, 
                                "link": link, 
                                "file_arsip": f"{ARCHIVE_FOLDER}/{nama_file}",
                                "waktu_crawl": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            }
                            database.append(entry)
                            notif_list.append(f"🔹 {judul}")
                            existing_urls.append(link)
                            print(f"Berhasil: {judul}")
        except Exception as e:
            print(f"Error pada {domain}: {e}")

    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(database, f, indent=4, ensure_ascii=False)

    if notif_list:
        msg = f"📰 <b>{len(notif_list)} Artikel Baru Ditemukan!</b>\n\n" + "\n".join(notif_list[:15])
        send_telegram(msg)
    else:
        print("Selesai. Tidak ada berita baru.")

if __name__ == "__main__":
    # Masukkan daftar link berita kampus yang ingin dipantau
    list_universitas = [
        "https://upb.ac.id/berita",
        "https://unnur.ac.id/berita",
        "https://utsmakassar.ac.id/berita"
    ]
    jalankan_crawler(list_universitas)
