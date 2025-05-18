import os
import time
import requests
import yaml
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from tqdm import tqdm
from urllib.parse import urlparse
import hashlib
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException

def load_config():
    print("Loading configuration...")
    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    print(f"Configuration loaded: {config}")
    return config

def setup_driver():
    print("Setting up Chrome driver...")
    chrome_options = Options()
    chrome_options.add_argument('--headless')  # Run in headless mode
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    print("Chrome driver setup completed")
    return driver

def download_image(url, save_path):
    print(f"Attempting to download image from: {url}")
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            # Generate a unique filename based on URL
            file_hash = hashlib.md5(url.encode()).hexdigest()
            file_extension = os.path.splitext(urlparse(url).path)[1]
            if not file_extension:
                file_extension = '.jpg'
            filename = f"{file_hash}{file_extension}"
            filepath = os.path.join(save_path, filename)
            
            with open(filepath, 'wb') as f:
                f.write(response.content)
            print(f"Successfully downloaded image to: {filepath}")
            return True
    except Exception as e:
        print(f"Error downloading {url}: {str(e)}")
    return False

def get_full_size_image(driver, img_element):
    try:
        print("Clicking on image to get full size version...")
        # 点击图片打开大图
        img_element.click()
        time.sleep(2)  # 等待大图加载
        
        print("Waiting for full size image to load...")
        # 等待大图加载完成，使用更可靠的选择器
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "img[jsname='kn3ccd']"))
        )
        
        # 获取大图URL
        full_img = driver.find_element(By.CSS_SELECTOR, "img[jsname='kn3ccd']")
        img_url = full_img.get_attribute('src')
        print(f"Found full size image URL: {img_url}")
        
        # 关闭大图预览
        print("Closing image preview...")
        close_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[aria-label='Close']"))
        )
        close_button.click()
        time.sleep(1)
        
        return img_url
    except Exception as e:
        print(f"Error getting full size image: {str(e)}")
        # 保存当前页面截图和源码以便调试
        driver.save_screenshot("error_screenshot.png")
        with open("error_page.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        print("Saved error screenshot and page source for debugging")
        return None

def main():
    print("Starting Google image crawler...")
    # 加载配置
    config = load_config()
    google_config = config['google']
    
    # Create save directory
    save_dir = os.path.join(config['common']['save_dir'], google_config['subdir'])
    os.makedirs(save_dir, exist_ok=True)
    print(f"Save directory created/verified: {save_dir}")
    
    # Setup Chrome driver
    driver = setup_driver()
    
    try:
        # Search for images
        search_term = google_config['keyword']
        url = f"https://www.google.com/search?q={search_term}&tbm=isch"
        print(f"Navigating to search URL: {url}")
        driver.get(url)
        
        try:
            print("Waiting for search results to load...")
            # 等待搜索结果加载，使用更可靠的选择器
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.isv-r"))
            )
            print("Search results loaded successfully")
            
            # 保存初始页面截图和源码以便调试
            driver.save_screenshot("initial_page.png")
            with open("initial_page.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            print("Saved initial page screenshot and source for debugging")
            
        except TimeoutException:
            print("Timeout: Search results not found, saving screenshot and HTML for debug.")
            driver.save_screenshot("google_debug.png")
            with open("google_debug.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            driver.quit()
            return
        
        # Scroll to load more images
        last_height = driver.execute_script("return document.body.scrollHeight")
        images_downloaded = 0
        images_processed = 0
        
        print(f"Starting to process images (skip: {google_config['skip']}, limit: {google_config['limit']})")
        with tqdm(total=google_config['limit'], desc="Downloading images") as pbar:
            while images_downloaded < google_config['limit']:
                # Scroll down
                print("Scrolling down to load more images...")
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                
                # 获取所有搜索结果图片，使用多个选择器尝试
                print("Finding image elements...")
                img_elements = []
                
                # 尝试不同的选择器
                selectors = [
                    "//div[contains(@class, 'isv-r')]//img[contains(@class, 'rg_i')]",
                    "//div[contains(@class, 'isv-r')]//g-img/img",
                    "//div[contains(@class, 'isv-r')]//img",
                    "//div[contains(@class, 'isv-r')]//a[contains(@href, '/imgres')]//img"
                ]
                
                for selector in selectors:
                    elements = driver.find_elements(By.XPATH, selector)
                    if elements:
                        print(f"Found {len(elements)} images using selector: {selector}")
                        img_elements = elements
                        break
                
                if not img_elements:
                    print("No images found with any selector, saving current page state...")
                    driver.save_screenshot("no_images_found.png")
                    with open("no_images_found.html", "w", encoding="utf-8") as f:
                        f.write(driver.page_source)
                    break
                
                # 处理每个搜索结果
                for img in img_elements:
                    if images_downloaded >= google_config['limit']:
                        break
                    
                    try:
                        # 跳过前面的图片
                        if images_processed < google_config['skip']:
                            print(f"Skipping image {images_processed + 1}")
                            images_processed += 1
                            continue
                        
                        print(f"Processing image {images_processed + 1}")
                        # 获取大图URL
                        full_img_url = get_full_size_image(driver, img)
                        
                        if full_img_url and full_img_url.startswith('http'):
                            if download_image(full_img_url, save_dir):
                                images_downloaded += 1
                                pbar.update(1)
                                print(f"Successfully downloaded image {images_downloaded} of {google_config['limit']}")
                        
                        images_processed += 1
                    except Exception as e:
                        print(f"Error processing image: {str(e)}")
                        continue
                
                # Check if we've reached the bottom
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    print("Reached bottom of page")
                    break
                last_height = new_height
                
    finally:
        print("Cleaning up and closing driver...")
        driver.quit()
        print("Crawler finished")

if __name__ == "__main__":
    main() 