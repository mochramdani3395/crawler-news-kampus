# Suteki News Radar (URL Harvester)

Automasi pengumpul URL berita dan isu terkini seputar ekosistem **Perguruan Tinggi di Indonesia** (SIAKAD Cloud, Neo Feeder PDDIKTI, Akreditasi/SPMI, Regulasi Kemdiktisaintek, PMB) berbasis **GitHub Actions** yang langsung disinkronkan ke **Google Sheets**.

Hasil di Google Sheets dirancang khusus untuk dianalisis, diberi skor relevansi, dan diekstrak menjadi draf artikel oleh **ChatGPT Web**.

---

## 🚀 Alur Kerja Sistem

```text
[ GitHub Actions (Cron 06:00 WIB) ]
                 │
                 ▼
[ Python Engine (harvester.py) ]
  - Menarik Google News RSS (Kata kunci khusus Suteki)
  - Menarik Direct RSS Media Edukasi Nasional
  - Anti-duplikasi URL otomatis
                 │
                 ▼
[ Google Sheets ('News_Radar') ]
  - Menyimpan URL, Judul, Tanggal, dan Tag Kategori
  - Menyediakan kolom kosong untuk ChatGPT
                 │
                 ▼
[ ChatGPT Web (Google Drive Access) ]
  - Membaca URL di Google Sheet
  - Mengisi Skor Relevansi, Skor Urgensi, & Rekomendasi Draf
```

---

## ⚙️ Konfigurasi Repository Secrets di GitHub

Agar GitHub Actions memiliki izin menulis ke Google Sheets Anda, tambahkan 2 rahasia di menu:
**GitHub Repository $\rightarrow$ Settings $\rightarrow$ Secrets and variables $\rightarrow$ Actions**:

1. **`SPREADSHEET_ID`**:
   ID dari Google Spreadsheet Anda (dapat dilihat pada URL browser antara `/d/` dan `/edit`).
   *Contoh:* `https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit` $\rightarrow$ ID-nya adalah `1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms`.

2. **`GCP_SA_KEY`**:
   Isi lengkap file kredensial JSON dari Google Cloud Service Account.
   *Penting:* Jangan lupa klik tombol **Share** di Google Spreadsheet Anda dan tambahkan email `client_email` Service Account tersebut sebagai **Editor**.

---

## 🤖 Menjalankan Manual (Uji Coba)

Selain berjalan otomatis setiap hari pukul **06:00 WIB**, Anda bisa memicu penarikan data kapan saja:
1. Buka tab **Actions** di repositori GitHub ini.
2. Pilih workflow **Suteki News Radar Harvester**.
3. Klik tombol **Run workflow** $\rightarrow$ **Run workflow**.

---

## 📝 Format Kolom di Google Sheets

| Kolom | Header | Keterangan |
| :---: | :--- | :--- |
| **A** | `Tanggal Input` | Tanggal data ditarik bot (YYYY-MM-DD) |
| **B** | `Sumber Media` | Portal berita (Kompas, Detik, Antara, dll) |
| **C** | `Judul Berita` | Judul artikel |
| **D** | `URL Berita` | Link asli berita (Aset utama untuk ChatGPT) |
| **E** | `Kata Kunci Terdeteksi` | Tag otomatis (SIAKAD, PDDIKTI, Akreditasi, dll) |
| **F** | `Skor Relevansi (1-10)` | Diisi oleh ChatGPT Web |
| **G** | `Skor Urgensi (1-10)` | Diisi oleh ChatGPT Web |
| **H** | `Rekomendasi Angle Konten`| Diisi oleh ChatGPT Web |
| **I** | `Status Tindak Lanjut` | Antrean / Siap Tulis / Abaikan |
