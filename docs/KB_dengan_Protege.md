# Knowledge base tunggal di Protégé

Sumber pengetahuan aktif adalah **`kb/enviropermit.ttl`**. Formatnya RDF/Turtle standar, mengikuti pola ekspor pada contoh `D:/OWLFiles/uts.ttl`: deklarasi OWL, restrictions, property chains, individu konsep, dan SWRL sebagai `swrl:Imp` dengan daftar body/head. Contoh tersebut hanya menjadi acuan format; aturan sejarah di dalamnya tidak disalin.

Sebelumnya aksioma kewajiban sudah berada di OWL, tetapi KB terpecah antara `.owl`, `.swrl`, dan JSON, serta beberapa pengecekan gap bukti masih spesifik domain dalam Python. Sekarang kondisi kewajiban, cabang dokumen, rule SWRL, persyaratan bukti, dan pemetaan sumber berada dalam TTL yang sama. File knowledge lama dihapus agar tidak ada dua sumber aktif.

## Membuka dan mengedit

1. Di Protégé, gunakan **File → Open** dan pilih `kb/enviropermit.ttl`.
2. Periksa **Classes**, **Object properties**, **Data properties**, dan **Individuals**. Restrictions, hierarchy, inverse, cardinality, disjointness, dan property chain menggunakan konstruk OWL biasa.
3. Tampilkan tab **SWRLTab/Rules** jika plugin SWRLTab tersedia. Rule `water-study-candidate` disimpan dalam format SWRL RDF, dengan `rdfs:label`, `rdfs:comment`, `source_id`, dan `swrla:isRuleEnabled`.
4. Individu `water_document_route` bertipe `DecisionQuery` menyimpan annotation `subjectClass`, `branchClass`, dan `missingEvidence`. Individu `EvidenceRequirement` menyimpan kondisi kebutuhan bukti. Edit melalui **Annotations**. Pemeriksaan ketiadaan bukti hanya menghasilkan gap/UNRESOLVED, bukan pengecualian hukum.
5. Simpan sebagai **Turtle**. Setelah perubahan KB, buat manifest release baru dengan SHA-256 file yang baru, lalu gunakan ID release itu pada konteks kasus. Engine menolak checksum yang tidak cocok; perubahan ontology tidak memerlukan kompilasi ulang Java.

Referensi `subjectClass`/`branchClass` harus berupa IRI kelas, kondisi properti harus menunjuk jenis properti yang sesuai. Loader menolak referensi yang tidak dikenal. IRI lengkap dipertahankan agar dua entitas dengan nama pendek sama tidak tertukar. Setiap rule memerlukan tepat satu label ID, dan maksimal satu `isRuleEnabled` bertipe boolean; nilai yang ambigu ditolak.

Checksum setelah menyimpan dari Protégé dapat dihitung dengan:

```powershell
(Get-FileHash kb/enviropermit.ttl -Algorithm SHA256).Hash.ToLower()
```

Gunakan nilai itu pada `checksums.knowledge_base` di manifest baru. Data kasus dan setiap observation yang dipakai harus menunjuk `kb_release_id` yang sama dengan manifest tersebut.

SWRL yang didukung engine T1: body berupa class/object-property atoms dan head berupa named class, dengan semua argumen head terikat oleh body. Jumlah rule tidak ditetapkan di kode. Built-ins, data-property atoms, dan head yang membuat nilai/individu baru belum didukung; engine menolak subset yang tidak didukung secara eksplisit. Ini batas eksekusi T1, bukan batas format Turtle/Protégé.

## Satu file penyimpanan, tahap reasoning terpisah

Loader membaca semua axioms dan SWRL dari TTL. Sebelum profile check/HermiT, loader mengeluarkan seluruh `SWRLRule` dari salinan ontology. `core-schema.owl` di direktori artefak merupakan **hasil ekstraksi**, bukan file KB yang diedit. OWLAPI memeriksa core tersebut sebagai OWL 2 DL; bukan keseluruhan file OWL+SWRL. Aturan aktif dieksekusi oleh SWRLAPI/Drools pada fakta bernama, lalu delta diperiksa lagi dengan HermiT. Snapshot, konflik, dan fixed-point limit tetap berlaku.

`cases/*.json` adalah data kasus terpisah agar bukti skenario lain tidak bercampur. Manifest `kb/releases/t1-water-spike-v2.json` hanya menunjuk file KB dan checksum/identitas rilis; tidak menyimpan rules. Request/response sekarang memakai schema `1.1` dengan satu `knowledge_base_path`.

Kode adapter masih memetakan field input ke vocabulary OWL dan menyiapkan individu kandidat. Engine masih menjalankan algoritma umum: validasi konteks/provenance, pemeriksaan konsistensi, materialisasi, dan pembacaan hasil. Kode tersebut tidak memilih cabang air limbah atau mengisi daftar kewajiban proyek melalui aturan `if/else`. Sumber keputusan domain dapat diedit di TTL.

Penambahan jenis field ke format `CaseSnapshot` dapat memerlukan mapping input baru. Antarmuka `infer(FactBundle, release)` dan CLI request JSON menerima asserted triples generik dengan vocabulary yang dideklarasikan dalam KB, sehingga penambahan aturan atas fakta yang tersedia tidak memerlukan perubahan adapter.

## Reproduksi

```powershell
./scripts/build_reasoner.ps1
.venv/Scripts/python.exe scripts/verify.py --output artifacts/ttl-verification-new
.venv/Scripts/python.exe -m enviropermit.cli --case cases/regression/water_spike/U.json --output artifacts/ttl-demo-U
```

Pakai direktori output baru/kosong. Test `tests/test_single_kb.py` membuktikan bahwa menonaktifkan rule, menambah rule kedua, dan mengubah persyaratan bukti **hanya di TTL** mengubah hasil tanpa perubahan kode engine. Validasi menggunakan parser OWLAPI dan SWRLAPI yang nyata; pengoperasian GUI Protégé belum diuji otomatis.

Hasil final 15 November 2026: **55 tes lulus** dalam 260,34 detik. Seluruh regresi T1 tetap lulus; A/B/U konsisten, C dikarantina. U tetap `UNRESOLVED`, dan kewajiban SLO proyek A tetap dihasilkan HermiT dari relasi kegiatan. Core yang diekstrak lolos OWL 2 DL tanpa pelanggaran. SWRL menghasilkan fakta kandidat yang tersimpan, lalu HermiT mengklasifikasinya kembali.

Ringkasan hasil tersedia di [TTL-results.json](verification/TTL-results.json). Perintah verifikasi menyimpan log, request/response, `core-schema.owl`, asserted/inferred OWL, dan delta SWRL di direktori output yang dipilih.
