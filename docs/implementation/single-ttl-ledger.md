# Centralisasi knowledge base sesuai permintaan pengguna

Desain yang diminta: satu TTL yang dapat diedit di Protégé. Contoh `D:/OWLFiles/uts.ttl` dibaca sebagai contoh format, bukan instruksi eksekusi atau domain yang akan disalin.

Langkah: tes perilaku RED; pindahkan TBox/RBox, individu konsep, SWRL standar, metadata keputusan dan gap ke satu TTL; ambil core tanpa SWRL saat runtime; gunakan loader aturan generik; pertahankan seluruh regresi dan jalankan review.

Data kasus tetap terpisah untuk isolasi snapshot. Manifest release hanya locator/checksum dan identitas versi, bukan rules. Tidak ada metadata Git di workspace.

- RED awal: 4 tes centralisasi gagal pada implementasi lama (`artifacts/single-ttl-red.txt`).
- Migrasi: satu `kb/enviropermit.ttl`, OWLAPI mengekstrak SWRL standar sebelum DL, rule discovery generik, evidence requirements dan source records dalam TTL. Path sumber lama dihapus; release v2/schema1.1 membedakan format baru.
- Smoke: 8 tes lulus, termasuk mematikan/menambah rule dan mengubah evidence gap hanya melalui TTL.
- Suite sebelum review-fix: 50 passed dalam 266.37s; A/B/U konsisten, C dikarantina (`artifacts/ttl-final`).
- Review independen read-only menemukan referensi metadata yang tidak divalidasi/IRI dipendekkan, serta anotasi enablement/ID rule ambigu. Kelima reproduksi gagal sesuai harapan (`artifacts/ttl-review-red.txt`), lalu diperbaiki dengan validasi jenis referensi, IRI penuh, dan kontrol anotasi tunggal bertipe benar.
- Ruling: subset SWRL tetap dibatasi pada atom kelas/relasi dan head kelas atas kandidat bernama; batas generik engine ini tidak memuat kondisi legal. Dukungan built-ins dan GUI Protégé aktual tidak diklaim. Domain hukum/komposisi/planner tetap task lanjutan.
- Final: kedua temuan review diperbaiki dalam satu pass; lima tes reproduksi RED→GREEN. Suite penuh **55/55 passed**, exit 0, 260.34s. Profil core dan contoh A/B/U/C diperiksa dari artefak `artifacts/ttl-reviewed`; hasil tersimpan di `docs/verification/TTL-results.json`. Tidak ada deferred minor.
