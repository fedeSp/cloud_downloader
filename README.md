# Cloud Downloader

Aplicación de escritorio para descargar carpetas de Google Drive (y próximamente OneDrive y Dropbox) sin necesidad de instalar clientes oficiales. Funciona mediante [rclone](https://rclone.org/) embebido, con una interfaz gráfica construida en Python + CustomTkinter.

---

## Características

- Descarga carpetas enteras de Google Drive con un par de clics
- Cola de descargas: agregá múltiples URLs/carpetas antes de iniciar
- Filtro por extensión (`pdf`, `mp4`, `docx`, etc.)
- Exportación de Google Docs a DOCX/XLSX/PPTX o PDF
- Soporte para modo claro/oscuro
- Autenticación OAuth via navegador (sin manejar credenciales manualmente)
- Binario portable: no requiere instalar Python ni rclone por separado

---

## Requisitos para ejecutar el ejecutable

- Windows 10/11 (64-bit) o macOS 12+
- Conexión a internet para la autenticación y las descargas

No se necesita instalar nada más. El ejecutable incluye Python y rclone embebidos.

---

## Uso

### 1. Descargá el ejecutable

Bajá la última versión desde [Releases](https://github.com/fedeSp/cloud_downloader/releases/latest).

| Plataforma | Archivo             |
|------------|---------------------|
| Windows    | `CloudDownloader.exe` |
| macOS      | `CloudDownloader.dmg` |

> **Windows:** si aparece "aplicación desconocida", hacé clic en **Más información → Ejecutar de todas formas**.  
> **macOS:** si aparece *"Apple could not verify..."*, **no** hagas doble clic. En cambio: **clic derecho → Abrir → Abrir**. Solo hay que hacerlo la primera vez.

### 2. Primera ejecución — conectar Google Drive

Al agregar una URL de Google Drive por primera vez, la app te va a pedir que conectes tu cuenta:

1. Hacé clic en **Conectar con Google Drive**
2. Se abre el navegador → iniciá sesión y autorizá el acceso
3. La ventana se actualiza automáticamente al confirmar

Solo hace falta hacerlo una vez. Las credenciales se guardan en `%APPDATA%\rclone\rclone.conf` (Windows) o `~/.config/rclone/rclone.conf` (macOS).

### 3. Agregar URLs a la cola

1. Copiá la URL de la carpeta de Google Drive  
   (ej: `https://drive.google.com/drive/folders/1AbC...XyZ`)
2. Pegala en el campo **URL / Ruta**
3. Hacé clic en **+ Agregar** y elegí la carpeta de destino local
4. Repetí para todas las carpetas que quieras descargar

### 4. Opciones (acordeón)

| Opción | Descripción |
|--------|-------------|
| **Filtrar extensiones** | Ingresá extensiones separadas por coma (`pdf, mp4`). Vacío = descarga todo. |
| **Google Docs** | Elegí el formato de exportación para archivos de Docs/Sheets/Slides. |

### 5. Descargar

Hacé clic en **Descargar todo**. El log muestra el progreso en tiempo real. Podés cancelar en cualquier momento con el botón **Cancelar**.

---

## Desarrollo

### Estructura del proyecto

```
cloud_downloader/
├── src/
│   ├── drive_downloader_ui.py   # Entry point — clase App
│   ├── config.py                # Configuración de proveedores y formatos
│   ├── rclone.py                # Utilidades rclone (paths, config, tokens)
│   ├── download.py              # Lógica de descarga (sin UI)
│   └── ui/
│       ├── auth_dialog.py       # Diálogo de autenticación OAuth
│       └── queue_panel.py       # Panel de cola de descargas
├── installer/
│   └── installer.iss            # Script Inno Setup (Windows)
├── drive_downloader.spec        # Configuración de PyInstaller
├── build_windows.ps1            # Script de build para Windows
├── build_mac.sh                 # Script de build para macOS
├── version.json                 # Versión actual de la app
└── requirements.txt             # Dependencias Python
```

### Instalación del entorno

```bash
pip install -r requirements.txt
```

### Ejecutar en modo desarrollo

```bash
python src/drive_downloader_ui.py
```

> La primera vez, descargá `rclone.exe` (Windows) o `rclone` (macOS) y colocalo en la raíz del proyecto, o instalalo globalmente en el sistema.

### Build — Windows

```powershell
.\build_windows.ps1
```

Genera `dist\CloudDownloader.exe`. Si tenés [Inno Setup 6](https://jrsoftware.org/isinfo.php) instalado, también genera el instalador en `dist\installer\CloudDownloader_Setup.exe`.

### Build — macOS

```bash
chmod +x build_mac.sh
./build_mac.sh
```

Genera `dist/CloudDownloader.app` y `dist/CloudDownloader.dmg`.

---

## Agregar un proveedor (OneDrive, Dropbox, etc.)

En `src/config.py`, descomentá o agregá una entrada en `PROVIDERS`:

```python
PROVIDERS = {
    "drive":    {"name": "Google Drive", "rclone_type": "drive",    "remote": "drive"},
    "onedrive": {"name": "OneDrive",     "rclone_type": "onedrive", "remote": "onedrive"},
    "dropbox":  {"name": "Dropbox",      "rclone_type": "dropbox",  "remote": "dropbox"},
}
```

Cada proveedor que rclone soporte puede agregarse de esta forma.

---

## Tecnologías

- [Python 3.8+](https://python.org)
- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) — UI moderna
- [rclone](https://rclone.org/) — motor de transferencia de archivos
- [PyInstaller](https://pyinstaller.org/) — empaquetado en ejecutable
- [Inno Setup](https://jrsoftware.org/isinfo.php) — instalador Windows (opcional)

---

## Licencia

MIT
