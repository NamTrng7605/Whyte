import os
import time
import json
import logging
import threading
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from core_engine import PhotoboothEngine
from dotenv import set_key

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("photobooth.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("PhotoboothApp")

app = FastAPI()
engine = PhotoboothEngine()

# Base directory of the script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Folders
PHOTOS_DIR = os.path.join(BASE_DIR, "Photos")
OUTPUT_DIR = os.path.join(BASE_DIR, "Output_ReadyToPrint")
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

# Ensure directories exist
for d in [PHOTOS_DIR, OUTPUT_DIR, STATIC_DIR]:
    os.makedirs(d, exist_ok=True)

# Templates
templates = Jinja2Templates(directory=TEMPLATES_DIR)

class PhotoboothHandler(FileSystemEventHandler):
    def __init__(self, engine):
        self.engine = engine
        self.photo_queue = []
        self.lock = threading.Lock()

    def on_created(self, event):
        if event.is_directory: return
        if event.src_path.lower().endswith(('.png', '.jpg', '.jpeg')):
            logger.info(f"New file detected: {event.src_path}")
            # Debounce: wait a bit for file to be fully written
            time.sleep(1)
            with self.lock:
                self.photo_queue.append(event.src_path)
                if len(self.photo_queue) >= 4:
                    self.process_batch()

    def process_batch(self):
        with self.lock:
            if len(self.photo_queue) < 4:
                return
            
            # Sort by creation time to be safe
            self.photo_queue.sort(key=os.path.getctime)
            batch = self.photo_queue[:4]
            self.photo_queue = self.photo_queue[4:]
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_name = f"photobooth_{timestamp}.jpg"
        output_path = os.path.join(OUTPUT_DIR, output_name)
        
        logger.info(f"Processing batch of 4 photos: {batch}")
        try:
            # 1. Xử lý ảnh ghép bố cục trực tiếp (Không có QR)
            self.engine.process_images(batch, output_path)
            
            # 2. Gửi thẳng lệnh in đến máy in hệ thống
            logger.info(f"Sending {output_path} to printer...")
            self.engine.print_image(output_path)
            
            logger.info("Batch processed successfully.")
        except Exception as e:
            logger.error(f"Error processing batch: {e}")

# Watchdog Observer
observer = Observer()
handler = PhotoboothHandler(engine)
observer.schedule(handler, PHOTOS_DIR, recursive=False)

@app.on_event("startup")
def startup_event():
    observer.start()
    logger.info("Watchdog observer started.")

@app.on_event("shutdown")
def shutdown_event():
    observer.stop()
    observer.join()
    logger.info("Watchdog observer stopped.")

# --- API Endpoints ---

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    settings = engine.load_settings()
    active_type = engine.active_frame_type
    return templates.TemplateResponse(
        request=request, 
        name="index.html", 
        context={
            "settings": settings, 
            "active_type": active_type,
            "engine": engine
        }
    )

@app.get("/api/settings")
async def get_settings():
    return engine.load_settings()

@app.post("/api/settings")
async def update_settings(new_settings: dict):
    try:
        with open(engine.settings_path, "w") as f:
            json.dump(new_settings, f, indent=4)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error saving settings: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.post("/api/set_active_type")
async def set_active_type(type: str):
    logger.info(f"Request to set active type to: {type}")
    engine.active_frame_type = type
    try:
        set_key(".env", "ACTIVE_FRAME_TYPE", type)
        logger.info(f"Updated .env with ACTIVE_FRAME_TYPE={type}")
    except Exception as e:
        logger.error(f"Error updating .env: {e}")
    return {"status": "success", "active_type": type}

@app.post("/api/print")
async def manual_print(request: Request):
    try:
        data = await request.json()
    except:
        data = {}
    
    layout_type = data.get("type", engine.active_frame_type)
    selected_photos = data.get("photos", [])
    
    if not selected_photos or len(selected_photos) < 4:
        return JSONResponse({"status": "error", "message": "Please select 4 photos from the gallery first"}, status_code=400)

    photo_paths = [os.path.join(PHOTOS_DIR, f) for f in selected_photos]
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_name = f"manual_print_{timestamp}.jpg"
    output_path = os.path.join(OUTPUT_DIR, output_name)
    
    logger.info(f"Manual print request for layout: {layout_type}")
    
    original_type = engine.active_frame_type
    engine.active_frame_type = layout_type
    
    try:
        # 1. Ghép ảnh theo layout lựa chọn
        engine.process_images(photo_paths, output_path)
        
        # 2. Tiến hành in bản hoàn thiện trực tiếp
        logger.info(f"Sending manual print {output_path} to printer...")
        success = engine.print_image(output_path)
        if success:
            return {"status": "success", "message": f"Successfully processed and sent to printer: {output_name}"}
        else:
            return JSONResponse({"status": "error", "message": "Printer error. Check logs."}, status_code=500)
    except Exception as e:
        logger.error(f"Manual print error: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    finally:
        engine.active_frame_type = original_type

# Serve folders
app.mount("/output", StaticFiles(directory=OUTPUT_DIR), name="output")
app.mount("/photos", StaticFiles(directory=PHOTOS_DIR), name="photos")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/api/list_frames")
async def list_frames():
    try:
        frames = [f for f in os.listdir("Frames") if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        return frames
    except Exception as e:
        logger.error(f"Error listing frames: {e}")
        return []

@app.post("/api/update_frame_path")
async def update_frame_path(request: Request):
    try:
        data = await request.json()
        layout_type = data.get("type")
        frame_name = data.get("frame")
        
        if not layout_type or not frame_name:
            return JSONResponse({"status": "error", "message": "Missing type or frame"}, status_code=400)
            
        settings = engine.load_settings()
        if layout_type in settings:
            settings[layout_type]["frame_path"] = f"Frames/{frame_name}"
            with open(engine.settings_path, "w") as f:
                json.dump(settings, f, indent=4)
            return {"status": "success"}
        else:
            return JSONResponse({"status": "error", "message": "Invalid layout type"}, status_code=400)
    except Exception as e:
        logger.error(f"Error updating frame path: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.get("/api/available_printers")
async def get_available_printers():
    return engine.list_printers()

@app.post("/api/set_printer")
async def set_printer(printer_name: str):
    logger.info(f"Setting printer to: {printer_name}")
    engine.printer_name = printer_name
    try:
        set_key(".env", "PRINTER_NAME", printer_name)
    except Exception as e:
        logger.error(f"Error updating .env for PRINTER_NAME: {e}")
    return {"status": "success", "printer_name": printer_name}

@app.post("/api/test_print")
async def test_print(printer_name: str):
    logger.info(f"Test print request for printer: {printer_name}")
    preview_path = os.path.join(OUTPUT_DIR, "preview_test.jpg")
    if not os.path.exists(preview_path):
        return JSONResponse({"status": "error", "message": "No preview image available to test print. Please generate a preview first."}, status_code=400)
    
    original_printer = engine.printer_name
    engine.printer_name = printer_name
    try:
        success = engine.print_image(preview_path)
        if success:
            return {"status": "success", "message": "Test print sent successfully."}
        else:
            return JSONResponse({"status": "error", "message": "Test print failed. Check logs."}, status_code=500)
    finally:
        engine.printer_name = original_printer

@app.get("/api/photos")
async def list_photos():
    try:
        all_files = os.listdir(PHOTOS_DIR)
        valid_photos = []
        
        for f in all_files:
            if f.lower().endswith(('.png', '.jpg', '.jpeg')):
                full_path = os.path.join(PHOTOS_DIR, f)
                try:
                    if os.path.isfile(full_path):
                        mtime = os.path.getmtime(full_path)
                        valid_photos.append((f, mtime))
                except (OSError, PermissionError):
                    continue
        
        valid_photos.sort(key=lambda x: x[1], reverse=True)
        return [photo[0] for photo in valid_photos[:20]]
    except Exception as e:
        logger.error(f"Error listing photos: {e}")
        return []

@app.post("/api/preview")
async def generate_preview(request: Request):
    try:
        data = await request.json()
    except:
        data = {}
    
    layout_type = data.get("type", engine.active_frame_type)
    selected_photos = data.get("photos", [])
    
    logger.info(f"Generating preview for layout: {layout_type}")
    
    if selected_photos:
        photo_paths = [os.path.join(PHOTOS_DIR, f) for f in selected_photos]
    else:
        input_photos = [os.path.join(PHOTOS_DIR, f) for f in os.listdir(PHOTOS_DIR) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        if len(input_photos) < 4:
            return JSONResponse({"status": "error", "message": f"Need at least 4 photos for preview (Found: {len(input_photos)})"}, status_code=400)
        input_photos.sort(key=os.path.getmtime, reverse=True)
        photo_paths = input_photos[:4]
    
    preview_path = os.path.join(OUTPUT_DIR, "preview_test.jpg")
    
    original_type = engine.active_frame_type
    engine.active_frame_type = layout_type
        
    try:
        engine.process_images(photo_paths, preview_path, is_preview=True)
        return {"status": "success", "preview_url": f"/output/preview_test.jpg?t={time.time()}"}
    except Exception as e:
        logger.error(f"Error generating preview: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    finally:
        engine.active_frame_type = original_type

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)