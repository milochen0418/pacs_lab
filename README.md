# PACS Lab

A Reflex app that starts practice PACS in Docker, fills them with DICOM
images, and shows the exact settings DICOM Data Explorer needs to use them.
It is meant for people who have never seen a PACS: a wizard does the work,
and every step says in plain words (繁體中文 or English) what happens.

## What it does

1. **Pick a kind of PACS** (each one is a Docker container):

   | Kind | What it is like | DICOMweb | C-GET | C-MOVE | Web page |
   |------|-----------------|----------|-------|--------|----------|
   | Orthanc (easy) | the most common open-source PACS, everything allowed | yes | yes | yes | yes |
   | Orthanc (strict) | like many hospitals: known AE titles only, no C-GET, at most 50 answers | yes | no | yes | yes |
   | Mini PACS | `mini_pacs.py` on pynetdicom: the DICOM network and nothing else | no | yes | yes | no |

   Orthanc is `orthancteam/orthanc:26.9.1` (Orthanc 1.13.0) with DICOMweb
   and the Stone Web Viewer on. The mini PACS image (`pacs-lab/mini-pacs:1`)
   is built on first use, through the re_ddns package cache when it runs.

2. **Pick the images**:
   - a starter set from IDC (public, CC BY): an abdominal CT with a kidney
     tumour SEG, a chest CT with a lung nodule SEG, a chest X-ray (108 MB,
     downloaded once into the lab's data folder);
   - series from the shared DICOM folder, e.g. what DICOM Data Explorer
     downloaded (read-only).

   By default the copies get new UIDs and made-up patients (LAB00001
   WANG^XIAOMING, ...): DICOM Data Explorer treats them as new series, and
   the patient IDs are something to search for. UIDs are remapped the same
   way across a batch, so a SEG still points at its CT. The made-up patients
   are kept in `patients.json`, so a real patient becomes the same made-up one
   in every practice PACS.

3. **Start**: pull or build the image, create the container (its files in
   the volume `<name>-data`), wait until it answers, put the images in
   (Orthanc's REST API, or C-STORE for the mini PACS), then test it the way
   DICOM Data Explorer will (DICOMweb search, C-ECHO and C-FIND as
   `DDE_EXPLORER`).

4. **Settings**: each PACS's page lists, field by field, what to type into
   DICOM Data Explorer's PACS form (with the form's own English labels and a
   copy button), what the PACS holds, a link to Orthanc's own web page, and
   the PACS's log.

### Where DICOM Data Explorer runs

The addresses depend on it, and so does where the PACS sends C-MOVE images:

| DICOM Data Explorer | Host or IP | Ports | C-MOVE goes to |
|---------------------|------------|-------|----------------|
| in the App Store (detected by its container) | the PACS container's name | 4242 / 8042 | `smart-app-dicom-data-explorer:11120` |
| on this computer (`reflex run`) | 127.0.0.1 | the ports published on this computer | `host.docker.internal:11120` |

A PACS page can switch between the two (the container is recreated, the
images stay). While the App Store's explorer holds port 11120 on this
computer, one started with `reflex run` needs another `DICOM_RECEIVER_PORT`;
start PACS Lab with the same number in `PACS_LAB_MAC_RECEIVER_PORT`.

Everything about a PACS is written on its container (labels, and the
Orthanc password in its environment), so the list always shows what Docker
really runs. Only containers labelled `pacs-lab.kind` are touched. Ports on
this computer are bound to 127.0.0.1 only.

## Running it

In the re_ddns App Store (catalog entry `pacs-lab`). It mounts
`/var/run/docker.sock`, so the app can start containers; that is full
control of Docker, which is why it only manages its own labelled ones. It
also gets read access to the `dicom` collection and a volume for its data.

On a Mac with Docker Desktop:

```bash
poetry env use python3.11
poetry install
poetry run reflex run --frontend-port 3500 --backend-port 8500
```

| Setting | Environment variable | Default |
|---------|----------------------|---------|
| Data folder (starter images, patients.json) | `PACS_LAB_DATA_DIR` | `~/.local/share/pacs_lab` |
| Shared DICOM folder | `DDNS_COLLECTIONS_ROOT` | `/Users/Shared/re-ddns/collections` on macOS |
| C-MOVE port of an explorer on this computer | `PACS_LAB_MAC_RECEIVER_PORT` | `11120` |

## Tests

```bash
poetry run pytest -q
```

They cover the relabelling (a SEG keeps pointing at its CT, the patient
book), what each kind of PACS is configured with, the settings cards for
both places, and the texts. The Docker parts were checked against Docker
Desktop: all three kinds created from the wizard, then set up in DICOM Data
Explorer with the values shown, searched, and downloaded over DICOMweb,
C-MOVE and C-GET.

## Data credits

The starter set comes from the NCI Imaging Data Commons: C4KC-KiTS
(KiTS-00061, CC BY 3.0), NLST and NLSTSeg (107610, CC BY 4.0), COVID-19-AR
(COVID-19-AR-16434356, CC BY 4.0).
