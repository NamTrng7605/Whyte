import os
import time
import json
import subprocess
# import qrcode
import logging
try:
    import win32print
except ImportError:
    win32print = None
from PIL import Image, ImageOps
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv(override=True)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("photobooth.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("PhotoboothEngine")

class PhotoboothEngine:
    def __init__(self):
        self.settings_path = "layout_settings.json"
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_KEY")
        self.printer_name = os.getenv("PRINTER_NAME")
        self.irfanview_path = os.getenv("IRFANVIEW_PATH")
        self.active_frame_type = os.getenv("ACTIVE_FRAME_TYPE", "PORTRAIT_STRIP")
        
        self.supabase: Client = None
        if self.supabase_url and self.supabase_key:
            try:
                self.supabase = create_client(self.supabase_url, self.supabase_key)
            except Exception as e:
                logger.error(f"Error connecting to Supabase: {e}")

    def list_printers(self):
        if not win32print:
            return ["Printer listing not available (win32print missing)"]
        
        printers = []
        try:
            # EnumPrinters: 2 means local/shared printers
            printer_info = win32print.EnumPrinters(2)
            for p in printer_info:
                # p[2] is the printer name
                printers.append(p[2])
        except Exception as e:
            logger.error(f"Error listing printers: {e}")
            return [f"Error listing printers: {e}"]
        return printers

    def load_settings(self):
        try:
            with open(self.settings_path, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading settings from {self.settings_path}: {e}")
            return {}

    # def generate_qr(self, url):
    #     qr = qrcode.QRCode(version=1, box_size=20, border=1)
    #     qr.add_data(url)
    #     qr.make(fit=True)
    #     return qr.make_image(fill_color="black", back_color="white")

    def upload_to_supabase(self, file_path, bucket_name="photos"):
        if not self.supabase:
            return None
        
        file_name = os.path.basename(file_path)
        try:
            with open(file_path, "rb") as f:
                self.supabase.storage.from_(bucket_name).upload(file_name, f)
                res = self.supabase.storage.from_(bucket_name).get_public_url(file_name)
                return res
        except Exception as e:
            logger.error(f"Supabase upload error: {e}")
            return None

def process_images(self, image_paths, output_path, is_preview=False):
        logger.info(f"Processing images with layout: {self.active_frame_type} (is_preview={is_preview})")
        settings = self.load_settings()
        frame_config = settings.get(self.active_frame_type)
        if not frame_config:
            raise ValueError(f"Invalid frame type: {self.active_frame_type}")

        canvas_size = tuple(frame_config["canvas_size"])
        logger.debug(f"Canvas size: {canvas_size}")
        
        # Use solid white background for canvas
        canvas = Image.new("RGB", canvas_size, (255, 255, 255))

        # --- BÍ QUYẾT TỐI ƯU TỐC ĐỘ NẰM Ở ĐÂY ---
        # Nếu đang kéo thả xem thử -> Dùng BILINEAR (Nhanh gấp 10 lần)
        # Nếu bấm in thật -> Dùng LANCZOS (Chậm nhưng Nét căng)
        resample_filter = Image.Resampling.BILINEAR if is_preview else Image.Resampling.LANCZOS

        # 1. Paste Photos
        slots = frame_config["slots"]
        
        # Double the images if it's a PORTRAIT_STRIP and we have 4 images for 8 slots
        final_image_paths = list(image_paths)
        if self.active_frame_type == "PORTRAIT_STRIP" and len(image_paths) == 4 and len(slots) == 8:
            logger.info("Duplicating photos for PORTRAIT_STRIP double strip.")
            final_image_paths = image_paths + image_paths # Duplicate the 4 photos
        
        for i, img_path in enumerate(final_image_paths):
            if i >= len(slots): break
            
            try:
                img = Image.open(img_path)
                # Fix orientation and color profile issues
                img = ImageOps.exif_transpose(img)
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                slot = slots[i]
                logger.debug(f"Pasting image {i} to slot {slot}")
                
                # Áp dụng filter thuật toán tùy theo tình trạng
                img_fitted = ImageOps.fit(img, (slot["w"], slot["h"]), resample_filter)
                
                # Paste directly to RGB canvas
                canvas.paste(img_fitted, (slot["x"], slot["y"]))
                
            except Exception as e:
                logger.error(f"Error processing image {img_path}: {e}")

        # 3. Paste Frame
        frame_path = frame_config["frame_path"]
        logger.debug(f"Looking for frame at: {frame_path}")
        
        search_paths = [frame_path, os.path.join(os.getcwd(), frame_path)]
        actual_frame_path = None
        for p in search_paths:
            if os.path.exists(p):
                actual_frame_path = p
                break

        if actual_frame_path:
            frame = Image.open(actual_frame_path).convert("RGBA")
            # Áp dụng filter thuật toán xử lý khung
            frame = frame.resize(canvas_size, resample_filter)
            canvas.paste(frame, (0, 0), frame)
            logger.debug(f"Frame pasted successfully.")
        else:
            logger.warning(f"FRAME NOT FOUND at any of these locations: {search_paths}")


        # --- TỐI ƯU BƯỚC LƯU FILE THEO MỤC ĐÍCH ---
        if is_preview:
            # Lưu chất lượng thấp (60%) không cần chuẩn in ấn để web load lên ngay lập tức
            canvas.save(output_path, "JPEG", quality=60, subsampling=2)
            logger.info(f"Preview collage generated SUPER FAST and saved to {output_path}")
        else:
            # Lưu chất lượng cực đại 95% + 300 DPI khi thực hiện lệnh in thật
            canvas.save(output_path, "JPEG", quality=95, subsampling=0, dpi=(300, 300))
            logger.info(f"Clean collage (No QR) saved to {output_path} (Waiting for upload & real QR)")

        return output_path

    # def add_qr_to_image(self, image_path, qr_url):
    #     logger.info(f"Adding QR code to {image_path} with URL: {qr_url}")
    #     settings = self.load_settings()
    #     frame_config = settings.get(self.active_frame_type)
    #     if not frame_config:
    #         return False

    #     try:
    #         img = Image.open(image_path)
    #         # Ensure it's in a mode that supports pasting RGBA
    #         if img.mode != 'RGB':
    #             img = img.convert('RGB')
            
    #         qr_slots = frame_config.get("qr_slots", [])
    #         for qr_slot in qr_slots:
    #             qr_img = self.generate_qr(qr_url).convert("RGBA")
    #             qr_img = qr_img.resize((qr_slot["size"], qr_slot["size"]), Image.Resampling.LANCZOS)
    #             # Paste QR (RGBA) on top using itself as mask
    #             img.paste(qr_img, (qr_slot["x"], qr_slot["y"]), qr_img)
    #             logger.debug(f"QR pasted at {qr_slot['x']}, {qr_slot['y']}")
            
    #         img.save(image_path, "JPEG", quality=95, subsampling=0, dpi=(300, 300))
    #         logger.info(f"Image updated with QR code: {image_path}")
    #         return True
    #     except Exception as e:
    #         logger.error(f"Error adding QR to image: {e}")
    #         return False

    def print_image(self, image_path):
        if not self.irfanview_path or not os.path.exists(self.irfanview_path):
            logger.error(f"IrfanView not found at {self.irfanview_path}. Please install it.")
            return False
        
        if not self.printer_name:
            logger.error("Printer name not configured.")
            return False

        # WORKAROUND: Some PDF printers/drivers fail to switch to landscape via CLI.
        # If the layout is landscape, we rotate the image 90 degrees and print as PORTRAIT.
        print_image_path = os.path.abspath(image_path)
        # Force orientation to 1 (Portrait) for the printer driver
        orientation = 1 

        if "LANDSCAPE" in self.active_frame_type:
            try:
                logger.info(f"Landscape layout detected. Rotating image for portrait printing workaround.")
                img = Image.open(image_path)
                # Rotate 90 degrees clockwise to fit portrait paper
                img_rotated = img.rotate(-90, expand=True)
                
                base, ext = os.path.splitext(image_path)
                print_image_path = f"{base}_rotated_print{ext}"
                img_rotated.save(print_image_path, "JPEG", quality=100, dpi=(300, 300))
                print_image_path = os.path.abspath(print_image_path)
                logger.debug(f"Saved rotated image to {print_image_path}")
            except Exception as e:
                logger.error(f"Error rotating image: {e}")
                # Fallback to original path if rotation fails
                print_image_path = os.path.abspath(image_path)

        settings_dir = os.path.abspath("IrfanViewSettings")
        ini_path = os.path.join(settings_dir, "i_view64.ini")
        
        logger.info(f"Active frame type is '{self.active_frame_type}'. Workaround active: Printing as Portrait (1)")
        
        try:
            if os.path.exists(ini_path):
                with open(ini_path, "r") as f:
                    lines = f.readlines()
                
                # Force Orientation=1 in the INI for this print job
                has_orientation = False
                new_lines = []
                for line in lines:
                    if line.strip().startswith("Orientation="):
                        new_lines.append(f"Orientation={orientation}\n")
                        has_orientation = True
                    else:
                        new_lines.append(line)
                
                if not has_orientation:
                    final_lines = []
                    for line in new_lines:
                        final_lines.append(line)
                        if line.strip() == "[Print]":
                            final_lines.append(f"Orientation={orientation}\n")
                    new_lines = final_lines

                with open(ini_path, "w") as f:
                    f.writelines(new_lines)
                logger.debug(f"Successfully updated {ini_path} with Orientation={orientation}")
        except Exception as e:
            logger.error(f"Error updating INI orientation: {e}")

        logger.info(f"Printing {print_image_path} using IrfanView to '{self.printer_name}'")
        
        # IrfanView Command Line for printing:
        command = f'"{self.irfanview_path}" "{print_image_path}" /ini="{settings_dir}" /print="{self.printer_name}"'
        logger.debug(f"Executing command: {command}")

        try:
            subprocess.run(command, check=True, shell=True)
            logger.info("Sent to printer via IrfanView.")
            return True
        except Exception as e:
            logger.error(f"IrfanView printing error: {e}")
            return False

if __name__ == "__main__":
    # Test block
    engine = PhotoboothEngine()
    print("Engine initialized.")
