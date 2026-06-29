# Scraper Debug Notebooks

Notebook di folder ini hanya untuk debugging list berita.

Aturan:
- Tidak scrape isi artikel.
- Tidak upload ke Supabase.
- Output utama adalah `page`, `published_date`, dan `title` yang dipotong.
- Gunakan audit `oldest date`, `last page`, dan `rows per month` untuk memastikan coverage 4 bulan ke belakang.

Catatan source:
- `malangtimes` memakai Playwright load-more; `page_num` di notebook adalah estimasi batch berdasarkan urutan hasil.
- `seputarmalang` saat ini list page bisa tidak menyediakan tanggal; jika tanggal kosong, itu limitation list page, bukan detail article.
