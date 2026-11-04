# Suteki News Radar (URL Harvester & AI Radar)

Automasi pengumpul URL berita dan isu terkini seputar ekosistem **Perguruan Tinggi di Indonesia** (SIAKAD Cloud, Neo Feeder PDDIKTI, Akreditasi BAN-PT/LAM, SPMI, Regulasi Kemdiktisaintek, PMB) berbasis **GitHub Actions** yang langsung disinkronkan ke **Google Sheets** dengan arsitektur **Two-Tier AI Scoring**.

---

## 🚀 Alur Kerja Sistem (Two-Tier AI Scoring)

```text
[ GitHub Actions (Cron 06:00 WIB / Manual Trigger) ]
                       │
                       ▼
         [ Python Engine (harvester.py) ]
  - Menarik Google News RSS (Kata kunci khusus Suteki)
  - Menarik Direct RSS Media Edukasi Nasional
  - Filter Recency (Maksimal 7 hari terakhir)
  - Ekstraksi Tanggal Terbit Aktual (WIB)
  - Anti-duplikasi URL otomatis berbasis Google Sheet
                       │
                       ▼
        [ Tier 1: Gemini Free Triage ]
  - Auto-fallback multi-model Flash (3.5-flash / 3.8-flash / 3.1-flash-lite)
  - Triage cepat skala 1-10 & catatan alasan awal
  - Full Backfill otomatis untuk baris yang belum dinilai
                       │
                       ▼
        [ Google Sheets ('News_Radar') ]
  - Tersinkronisasi rapi lengkap dengan Tanggal Terbit
  - Kolom editorial disiapkan untuk review mendalam
                       │
                       ▼
        [ Tier 2: ChatGPT Web / Suteki Content Engine ]
  - Deep-dive analisis editorial & rekomendasi angle
  - Produksi artikel resmi blog Suteki, GDocs, & ClickUp
```

---

## ⚙️ Konfigurasi Repository Secrets di GitHub

Di menu **GitHub Repository $\rightarrow$ Settings $\rightarrow$ Secrets and variables $\rightarrow$ Actions**:

1. **`SPREADSHEET_ID`**: ID Google Spreadsheet (dari URL `/d/{SPREADSHEET_ID}/edit`).
2. **`GCP_SA_KEY`**: Isi lengkap file JSON kredensial Service Account Google Cloud.
   *Penting:* Pastikan email bot Service Account (`client_email`) telah diundang ke Google Spreadsheet sebagai **Editor**.
3. **`GEMINI_API_KEY`**: API Key gratis dari [Google AI Studio](https://aistudio.google.com/).

---

## 🤖 Menjalankan Manual (Uji Coba / Backfill)

Selain berjalan otomatis setiap hari pukul **06:00 WIB**, Anda bisa memicu penarikan data kapan saja:
1. Buka tab **Actions** di repositori GitHub ini.
2. Pilih workflow **Suteki News Radar Harvester**.
3. Klik tombol **Run workflow** $\rightarrow$ **Run workflow**.

---

## 📝 Format Kolom di Google Sheets

| Kolom | Header | Keterangan |
| :---: | :--- | :--- |
| **A** | `Tanggal Terbit` | Waktu posting aktual artikel berita (YYYY-MM-DD HH:MM WIB) |
| **B** | `Sumber Media` | Portal berita (Kompas, Detik, Antara, Sindonews, dll) |
| **C** | `Judul Berita` | Judul artikel berita |
| **D** | `URL Berita` | Link artikel asli (Kunci anti-duplikasi & riset ChatGPT) |
| **E** | `Kata Kunci Terdeteksi` | Kategori (SIAKAD, PDDIKTI, Akreditasi, Regulasi, PMB) |
| **F** | `Skor Awal Bot (1-10)` | **Tier 1**: Scoring triage otomatis oleh Gemini |
| **G** | `Catatan Awal Bot` | **Tier 1**: Alasan singkat penilaian relevansi |
| **H** | `Skor Final Editorial` | **Tier 2**: Review mendalam oleh ChatGPT / Redaksi |
| **I** | `Rekomendasi Angle Suteki`| **Tier 2**: Usulan sudut pandang konten blog Suteki |
| **J** | `Status Tindak Lanjut` | Antrean / Siap Tulis / Diterbitkan / Abaikan |
