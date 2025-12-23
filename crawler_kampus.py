import trafilatura
from trafilatura.spider import focused_crawler
import json
import os
import requests
import re
from datetime import datetime

# --- KONFIGURASI ---
TELEGRAM_TOKEN = "GANTI_DENGAN_TOKEN_BOT_ANDA"
TELEGRAM_CHAT_ID = "GANTI_DENGAN_CHAT_ID_ANDA"
DB_FILE = "database_artikel.json"
ARCHIVE_FOLDER = "arsip_artikel"

if not os.path.exists(ARCHIVE_FOLDER):
    os.makedirs(ARCHIVE_FOLDER)

def slugify(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text).strip('-')
    return text[:50]

def save_as_markdown(judul, isi, tanggal, penulis, link):
    clean_title = slugify(judul)
    date_prefix = datetime.now().strftime('%Y%m%d')
    filename = f"{date_prefix}-{clean_title}.md"
    filepath = os.path.join(ARCHIVE_FOLDER, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# {judul}\n\n- **Sumber:** {link}\n- **Penulis:** {penulis}\n- **Tanggal Posting:** {tanggal}\n- **Waktu Crawl:** {datetime.now()}\n\n---\n\n{isi}")
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
            # PERBAIKAN DI SINI: Cara memanggil focused_crawler yang benar
            links, _ = focused_crawler(domain, max_seen_urls=10)
            
            if links:
                for link in links:
                    if link not in existing_urls:
                        downloaded = trafilatura.fetch_url(link)
                        result = trafilatura.extract(downloaded, output_format='json', include_comments=False)
                        if result:
                            data = json.loads(result)
                            judul = data.get('title', 'Tanpa Judul')
                            nama_file = save_as_markdown(judul, data.get('text', ''), data.get('date', 'N/A'), data.get('author', 'Humas'), link)
                            entry = {"judul": judul, "link": link, "file_arsip": f"{ARCHIVE_FOLDER}/{nama_file}"}
                            database.append(entry)
                            notif_list.append(f"🔹 {judul}")
                            existing_urls.append(link)
        except Exception as e:
            print(f"Error pada {domain}: {e}")

    with open(DB_FILE, "w", encoding="utf-8") as f: json.dump(database, f, indent=4)

    if notif_list:
        msg = f"📰 <b>{len(notif_list)} Artikel Baru!</b>\n\n" + "\n".join(notif_list[:15])
        send_telegram(msg)
    else:
        print("Selesai. Tidak ada berita baru.")

if __name__ == "__main__":
    list_universitas = [
        "https://upb.ac.id/berita",
        "https://unnur.ac.id/berita",
        "https://utsmakassar.ac.id/berita"
    ]
    jalankan_crawler(list_universitas)
