import os
import time
import requests
import logging
from datetime import datetime
from urllib.parse import urljoin
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from tqdm import tqdm
import json
import io
import re
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# 创建必要的目录
def create_directories():
    """创建必要的目录结构"""
    directories = {
        'logs': 'logs',                    # 日志文件目录
        'debug_html': 'debug_html',        # 调试HTML文件目录
        'downloads': 'downloads',          # 下载的图片目录
        'records': 'records'               # 下载记录文件目录
    }
    
    for dir_name, dir_path in directories.items():
        os.makedirs(dir_path, exist_ok=True)
        print(f"确保目录存在: {dir_path}")

# 配置日志
def setup_logging(keyword):
    """配置日志系统"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"logs/bing_crawler_{keyword}_{timestamp}.log"
    
    # 清除之前的处理器
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    
    # 配置新的日志处理器
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    print(f"日志文件: {log_filename}")

def load_downloaded_urls(keyword):
    """加载已下载的URL记录"""
    record_file = f"records/bing_{keyword}_downloads.json"
    if os.path.exists(record_file):
        try:
            with open(record_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"读取下载记录失败: {e}")
            return {}
    return {}

def save_downloaded_url(keyword, url, filename):
    """保存已下载的URL记录"""
    record_file = f"records/bing_{keyword}_downloads.json"
    records = load_downloaded_urls(keyword)
    
    records[url] = {
        'filename': filename,
        'download_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    try:
        with open(record_file, 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"保存下载记录失败: {e}")

def save_error_page(driver, url, error_type):
    """保存错误页面的HTML内容"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 保存HTML
    html_filename = f"debug_html/error_{error_type}_{timestamp}.html"
    with open(html_filename, 'w', encoding='utf-8') as f:
        f.write(driver.page_source)
    
    # 保存截图
    screenshot_filename = f"debug_html/error_{error_type}_{timestamp}.png"
    driver.save_screenshot(screenshot_filename)
    
    logging.error(f"页面保存成功 - HTML: {html_filename}, 截图: {screenshot_filename}")
    logging.error(f"问题URL: {url}")

def get_image_size_from_headers(url, timeout=10):
    """从图片URL的headers中获取图片尺寸"""
    try:
        logging.debug(f"正在检查图片尺寸: {url}")
        # 只获取headers，不下载内容
        response = requests.head(url, timeout=timeout)
        response.raise_for_status()
        
        # 尝试从Content-Type获取图片类型
        content_type = response.headers.get('Content-Type', '')
        if not content_type.startswith('image/'):
            logging.warning(f"非图片类型: {url}, Content-Type: {content_type}")
            return None, None
            
        # 尝试从Content-Length获取文件大小
        content_length = int(response.headers.get('Content-Length', 0))
        if content_length < 1024:  # 小于1KB的可能是无效图片
            logging.warning(f"图片太小: {url}, 大小: {content_length}字节")
            return None, None
            
        # 获取图片尺寸
        width = None
        height = None
        
        # 尝试从URL中获取尺寸信息
        size_match = re.search(r'w=(\d+)&h=(\d+)', url)
        if size_match:
            width = int(size_match.group(1))
            height = int(size_match.group(2))
            logging.debug(f"从URL获取到图片尺寸: {url}, {width}x{height}")
        
        return width, height
    except Exception as e:
        logging.error(f"获取图片尺寸失败: {url}, 错误: {e}")
        return None, None

def is_valid_image(url, min_size=(512, 512), timeout=10):
    """验证图片URL是否有效且满足尺寸要求"""
    width, height = get_image_size_from_headers(url, timeout)
    if width is None or height is None:
        logging.warning(f"无法获取图片尺寸: {url}")
        return False
    is_valid = width >= min_size[0] and height >= min_size[1]
    if not is_valid:
        logging.warning(f"图片尺寸不满足要求: {url}, 当前尺寸: {width}x{height}, 最小要求: {min_size[0]}x{min_size[1]}")
    return is_valid

def is_broken_image(url):
    """检查是否是裂图URL"""
    broken_patterns = [
        r'https://th\.bing\.com/th/id/.*\?cb=iwp2',
        r'https://th\.bing\.com/th/id/.*\?rs=1',
        r'https://th\.bing\.com/th/id/.*\?pid=ImgDetMain'
    ]
    return any(re.search(pattern, url) for pattern in broken_patterns)

def download_image(url, timeout=10, max_retries=3):
    """下载图片并返回内容和大小"""
    start_time = time.time()
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            logging.info(f"开始下载图片: {url} (尝试 {retry_count + 1}/{max_retries})")
            response = requests.get(url, timeout=timeout, stream=True)
            response.raise_for_status()
            
            # 获取文件大小
            total_size = int(response.headers.get('content-length', 0))
            
            # 读取内容
            content = response.content
            
            # 计算下载速度
            download_time = time.time() - start_time
            speed = total_size / (1024 * 1024 * download_time) if download_time > 0 else 0  # MB/s
            
            logging.info(f"图片下载成功: {url}, 大小: {total_size/1024:.1f}KB, 速度: {speed:.2f}MB/s")
            return content, total_size, speed, download_time
        except Exception as e:
            retry_count += 1
            if retry_count < max_retries:
                logging.warning(f"下载失败，准备重试 ({retry_count}/{max_retries}): {url}, 错误: {e}")
                time.sleep(1)  # 等待1秒后重试
            else:
                logging.error(f"下载图片失败，已达到最大重试次数: {url}, 错误: {e}")
                raise

def setup_driver():
    """设置并返回WebDriver"""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    try:
        # 首先尝试使用 ChromeDriverManager
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    except Exception as e:
        logging.warning(f"ChromeDriverManager 安装失败: {e}")
        try:
            # 如果失败，尝试直接使用 Chrome
            driver = webdriver.Chrome(options=options)
        except Exception as e:
            logging.error(f"Chrome 启动失败: {e}")
            raise
    
    return driver

def crawl_bing_images(keyword, limit=10):
    # 创建必要的目录
    create_directories()
    
    # 设置日志
    setup_logging(keyword)
    
    start_time = time.time()
    logging.info(f"开始下载关键词 '{keyword}' 的图片，目标数量: {limit}")
    
    # 加载已下载的URL记录
    downloaded_urls = load_downloaded_urls(keyword)
    logging.info(f"已下载图片数量: {len(downloaded_urls)}")
    
    driver = setup_driver()
    base_url = "https://www.bing.com/images/search?q=" + keyword
    logging.debug(f"访问搜索页面: {base_url}")
    driver.get(base_url)

    time.sleep(3)  # 等待页面加载

    # 滚动几次加载更多结果
    logging.info("开始滚动页面加载更多图片...")
    scroll_start = time.time()
    for i in range(3):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        logging.debug(f"完成第 {i+1}/3 次滚动")
    logging.info(f"页面滚动完成，耗时: {time.time() - scroll_start:.2f}秒")

    # 找到所有 a 标签，aria-label 匹配的
    a_tags = driver.find_elements(By.XPATH, f"//a[contains(@aria-label, '{keyword} 的图像结果')]")
    logging.info(f"找到 {len(a_tags)} 个图像详情链接")

    base_dir = f"downloads/bing_{keyword}"
    os.makedirs(base_dir, exist_ok=True)
    logging.info(f"创建保存目录: {base_dir}")

    downloaded = 0
    total_download_size = 0
    with tqdm(total=min(len(a_tags), limit), desc="下载进度") as pbar:
        for a in a_tags:
            if downloaded >= limit:
                break

            href = a.get_attribute("href")
            if not href:
                continue

            detail_url = urljoin("https://www.bing.com", href)
            logging.debug(f"处理详情页: {detail_url}")
            try:
                driver.execute_script("window.open(arguments[0]);", detail_url)
                driver.switch_to.window(driver.window_handles[-1])
                # 增加页面加载等待时间
                time.sleep(5)  # 从2秒增加到5秒

                # 找到 .mainContainer 下的第一个 img
                try:
                    # 等待容器加载
                    container = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CLASS_NAME, "mainContainer"))
                    )
                    # 等待图片加载
                    img = WebDriverWait(container, 10).until(
                        EC.presence_of_element_located((By.TAG_NAME, "img"))
                    )
                    img_url = img.get_attribute("src")
                    
                    if img_url and img_url.startswith("http"):
                        logging.info(f"找到图片链接: {img_url}")
                        
                        # 检查是否是裂图
                        if is_broken_image(img_url):
                            logging.warning(f"检测到裂图URL: {img_url}")
                            # 刷新页面重试
                            driver.refresh()
                            time.sleep(5)  # 从2秒增加到5秒
                            # 重新等待图片加载
                            container = WebDriverWait(driver, 10).until(
                                EC.presence_of_element_located((By.CLASS_NAME, "mainContainer"))
                            )
                            img = WebDriverWait(container, 10).until(
                                EC.presence_of_element_located((By.TAG_NAME, "img"))
                            )
                            img_url = img.get_attribute("src")
                            if is_broken_image(img_url):
                                logging.error(f"刷新后仍然是裂图: {img_url}")
                                pbar.update(1)
                                continue
                            else:
                                logging.info(f"刷新后获取到新图片链接: {img_url}")
                        
                        # 检查是否已下载
                        if img_url in downloaded_urls:
                            logging.debug(f"跳过已下载的图片: {img_url}")
                            pbar.update(1)
                            continue

                        try:
                            img_data, size, speed, download_time = download_image(img_url)
                            filename = f"{downloaded + 1}.jpg"
                            filepath = os.path.join(base_dir, filename)
                            with open(filepath, "wb") as f:
                                f.write(img_data)
                            
                            # 保存下载记录
                            save_downloaded_url(keyword, img_url, filename)
                            
                            total_download_size += size
                            logging.info(f"图片 {downloaded + 1} 下载成功 - 大小: {size/1024:.1f}KB, 速度: {speed:.2f}MB/s, 耗时: {download_time:.2f}秒")
                            downloaded += 1
                            pbar.update(1)
                            # 更新进度条描述，显示预计剩余时间
                            avg_time = (time.time() - start_time) / downloaded
                            remaining = avg_time * (limit - downloaded)
                            pbar.set_description(f"下载进度 (预计剩余: {remaining:.1f}秒)")
                        except Exception as e:
                            logging.error(f"下载图片失败: {e}")
                            save_error_page(driver, detail_url, "download_failed")
                            pbar.update(1)
                            continue
                    else:
                        logging.warning(f"无效的图片链接: {img_url}")
                except Exception as e:
                    logging.error(f"等待页面元素超时: {e}")
                    save_error_page(driver, detail_url, "timeout_error")
                    pbar.update(1)
                    continue
            except Exception as e:
                logging.error(f"处理页面失败：{detail_url}，原因：{e}")
                save_error_page(driver, detail_url, "page_error")
                pbar.update(1)
            finally:
                driver.close()
                driver.switch_to.window(driver.window_handles[0])

    driver.quit()
    total_time = time.time() - start_time
    avg_speed = total_download_size / (1024 * 1024 * total_time) if total_time > 0 else 0
    logging.info(f"下载完成！共下载 {downloaded} 张图片，总大小: {total_download_size/1024/1024:.1f}MB")
    logging.info(f"总耗时: {total_time:.2f}秒，平均下载速度: {avg_speed:.2f}MB/s")
    logging.info(f"图片保存在目录：{base_dir}/")

if __name__ == "__main__":
    crawl_bing_images("泥土", limit=5)
