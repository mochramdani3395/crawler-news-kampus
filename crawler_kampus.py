import trafilatura
import json
import os
import requests
import re
from datetime import datetime

# --- KONFIGURASI ---
TELEGRAM_TOKEN = "8031042382:AAEvewZRUM1M-PNPHVru0DNkHaSSw9SwbkE"
TELEGRAM_CHAT_ID = "803153427"
DB_FILE = "database_artikel.json"
ARCHIVE_FOLDER = "arsip_artikel"

# Pastikan folder arsip tersedia
if not os.path.exists(ARCHIVE_FOLDER):
    os.makedirs(ARCHIVE_FOLDER)

def slugify(text):
    # Membersihkan judul agar aman jadi nama file
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text).strip('-')
    return text[:50] # Potong agar nama file tidak terlalu panjang

def save_as_markdown(judul, isi, tanggal, penulis, link):
    # Format Nama File: YYYYMMDD-judul-slug.md
    clean_title = slugify(judul)
    date_prefix = datetime.now().strftime('%Y%m%d')
    filename = f"{date_prefix}-{clean_title}.md"
    filepath = os.path.join(ARCHIVE_FOLDER, filename)
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# {judul}\n\n")
        f.write(f"- **Sumber:** {link}\n")
        f.write(f"- **Penulis:** {penulis}\n")
        f.write(f"- **Tanggal Posting:** {tanggal}\n")
        f.write(f"- **Tanggal Crawling:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"---\n\n")
        f.write(isi)
    return filename

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        requests.post(url, data=payload)
    except:
        pass

def jalankan_crawler(daftar_web):
    # Load history untuk cek duplikat
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f: database = json.load(f)
    else:
        database = []

    existing_urls = [item['link'] for item in database]
    artikel_baru_count = 0
    notif_list = []

    for domain in daftar_web:
        print(f"Mengecek: {domain}")
        try:
            links = trafilatura.spider.focused_crawler(domain, max_seen_urls=10)[0]
            for link in links:
                if link not in existing_urls:
                    downloaded = trafilatura.fetch_url(link)
                    result = trafilatura.extract(downloaded, output_format='json', include_comments=False)
                    
                    if result:
                        data = json.loads(result)
                        judul = data.get('title', 'Tanpa Judul')
                        
                        # 1. Simpan Konten Lengkap ke file .md
                        nama_file = save_as_markdown(
                            judul, 
                            data.get('text', ''), 
                            data.get('date', 'N/A'),
                            data.get('author', 'Humas'),
                            link
                        )
                        
                        # 2. Simpan Metadata ke JSON
                        entry = {
                            "judul": judul,
                            "tanggal_posting": data.get('date'),
                            "file_arsip": f"{ARCHIVE_FOLDER}/{nama_file}",
                            "link": link,
                            "waktu_crawl": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        }
                        database.append(entry)
                        notif_list.append(f"🔹 {judul}")
                        artikel_baru_count += 1
                        existing_urls.append(link)
        except Exception as e:
            print(f"Error pada {domain}: {e}")

    # Simpan database JSON
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(database, f, indent=4, ensure_ascii=False)

    # Kirim notifikasi Telegram (Hanya Judul)
    if notif_list:
        header = f"📰 <b>{artikel_baru_count} Artikel Baru Berhasil Diarsipkan!</b>\n\n"
        isi_notif = "\n".join(notif_list[:15]) # Maksimal 15 judul agar tidak kepanjangan
        if artikel_baru_count > 15:
            isi_notif += f"\n\n<i>...dan {artikel_baru_count - 15} artikel lainnya.</i>"
        send_telegram(header + isi_notif)
    else:
        print("Selesai. Tidak ada berita baru.")

if __name__ == "__main__":
    list_universitas = [
        "https://www.itb.ac.id/news",
        "https://ugm.ac.id/id/berita",
        "https://www.ui.ac.id/berita"
    ]
    jalankan_crawler(list_universitas)
