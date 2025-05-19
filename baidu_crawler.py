from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time
import os
import requests
import logging
from datetime import datetime
from tqdm import tqdm
import json
import urllib.parse
import random
import cv2
import numpy as np
import argparse

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
    log_filename = f"logs/baidu_crawler_{keyword}_{timestamp}.log"
    
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

# 创建全局session对象
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Referer': 'https://image.baidu.com/',
    'Connection': 'keep-alive'
})

def load_downloaded_urls(keyword):
    """加载已下载的URL记录"""
    record_file = f"records/baidu_{keyword}_downloads.json"
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
    record_file = f"records/baidu_{keyword}_downloads.json"
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

def download_image(url, timeout=10):
    """下载图片并返回内容和大小"""
    start_time = time.time()
    try:
        response = session.get(url, timeout=timeout, stream=True)
        response.raise_for_status()
        
        # 获取文件大小
        total_size = int(response.headers.get('content-length', 0))
        
        # 读取内容
        content = response.content
        
        # 计算下载速度
        download_time = time.time() - start_time
        speed = total_size / (1024 * 1024 * download_time) if download_time > 0 else 0  # MB/s
        
        return content, total_size, speed, download_time
    except Exception as e:
        logging.error(f"下载图片失败: {url}, 错误: {e}")
        raise

def download_images_from_baidu(keyword, num_images):
    # 创建必要的目录
    create_directories()
    
    # 设置日志
    setup_logging(keyword)
    
    start_time = time.time()
    logging.info(f"开始下载关键词 '{keyword}' 的图片，目标数量: {num_images}")
    
    # 加载已下载的URL记录
    downloaded_urls = load_downloaded_urls(keyword)
    logging.info(f"已下载图片数量: {len(downloaded_urls)}")
    
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')

    driver = webdriver.Chrome(options=chrome_options)
    base_dir = f"downloads/baidu_{keyword}"
    invalid_dir = os.path.join(base_dir, "invalid")
    os.makedirs(base_dir, exist_ok=True)
    os.makedirs(invalid_dir, exist_ok=True)
    logging.info(f"创建保存目录: {base_dir} 和 {invalid_dir}")

    search_url = f"https://image.baidu.com/search/index?tn=baiduimage&word={urllib.parse.quote(keyword)}"
    logging.debug(f"访问搜索页面: {search_url}")
    driver.get(search_url)
    time.sleep(2)

    # 模拟滚动加载内容
    logging.info("开始滚动页面加载更多图片...")
    scroll_start = time.time()
    for i in range(10):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1.5)
        logging.debug(f"完成第 {i+1}/10 次滚动")
    logging.info(f"页面滚动完成，耗时: {time.time() - scroll_start:.2f}秒")

    # 获取所有 a 标签
    logging.debug("开始提取图片详情链接...")
    links = driver.find_elements(By.TAG_NAME, "a")
    detail_links = []
    for a in links:
        href = a.get_attribute("href")
        if href and href.startswith("https://image.baidu.com/search/detail"):
            detail_links.append(href)

    logging.info(f"共找到 {len(detail_links)} 个详情链接")

    # 去重并限制数量
    seen = set()
    filtered_links = []
    for link in detail_links:
        if link not in seen:
            filtered_links.append(link)
            seen.add(link)
        if len(filtered_links) >= num_images:
            break

    logging.info(f"去重后剩余 {len(filtered_links)} 个链接")

    image_count = 0
    total_download_size = 0
    with tqdm(total=len(filtered_links), desc="下载进度") as pbar:
        for url in filtered_links:
            try:
                download_start = time.time()
                driver.get(url)
                time.sleep(2)

                try:
                    # 使用title属性定位图片元素
                    img_element = driver.find_element(By.CSS_SELECTOR, "img[title='点击查看图片来源']")
                    
                    # 获取图片尺寸
                    # width = img_element.get_attribute("width")
                    # height = img_element.get_attribute("height")
                    
                    # # 如果无法从属性获取尺寸，尝试从style属性获取
                    # if not width or not height:
                    #     style = img_element.get_attribute("style")
                    #     if style:
                    #         import re
                    #         width_match = re.search(r'width:\s*(\d+)px', style)
                    #         height_match = re.search(r'height:\s*(\d+)px', style)
                    #         if width_match and height_match:
                    #             width = width_match.group(1)
                    #             height = height_match.group(1)
                    
                    img_url = img_element.get_attribute("src")
                    if not img_url:
                        # 如果src为空，尝试获取data-src属性
                        img_url = img_element.get_attribute("data-src")
                except Exception as e:
                    logging.error(f"无法找到图片元素: {e}")
                    save_error_page(driver, url, "no_image_element")
                    pbar.update(1)
                    continue

                if img_url and img_url.startswith("http"):
                    # 检查是否已下载
                    if img_url in downloaded_urls:
                        logging.debug(f"跳过已下载的图片: {img_url}")
                        pbar.update(1)
                        continue

                    try:
                        img_data, size, speed, download_time = download_image(img_url)
                        
                        # 使用OpenCV检查图片尺寸
                        nparr = np.frombuffer(img_data, np.uint8)
                        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        if img is None:
                            raise Exception("无法解码图片")
                        height, width = img.shape[:2]
                        
                        # 生成文件名：unix时间戳 + 随机数
                        timestamp = int(time.time())
                        random_num = random.randint(1000, 9999)
                        filename = f"{timestamp}_{random_num}.jpg"
                        
                        # 根据尺寸决定保存位置
                        if width >= 512 and height >= 512:
                            filepath = os.path.join(base_dir, filename)
                        else:
                            filepath = os.path.join(invalid_dir, filename)
                            logging.info(f"图片尺寸不符合要求 ({width}x{height})，保存到invalid目录")
                        
                        with open(filepath, "wb") as f:
                            f.write(img_data)
                        
                        # 保存下载记录
                        save_downloaded_url(keyword, img_url, filename)
                        
                        total_download_size += size
                        logging.info(f"图片 {filename} 下载成功 - 大小: {size/1024:.1f}KB, 速度: {speed:.2f}MB/s, 耗时: {download_time:.2f}秒")
                        image_count += 1
                        pbar.update(1)
                        # 更新进度条描述，显示预计剩余时间
                        avg_time = (time.time() - start_time) / image_count
                        remaining = avg_time * (len(filtered_links) - image_count)
                        pbar.set_description(f"下载进度 (预计剩余: {remaining:.1f}秒)")
                    except Exception as e:
                        logging.error(f"下载图片失败: {e}")
                        save_error_page(driver, url, "download_failed")
                        pbar.update(1)
                        continue

            except Exception as e:
                logging.error(f"处理页面失败：{url}，原因：{e}")
                save_error_page(driver, url, "page_error")
                pbar.update(1)
                continue

    driver.quit()
    total_time = time.time() - start_time
    avg_speed = total_download_size / (1024 * 1024 * total_time) if total_time > 0 else 0
    logging.info(f"下载完成！共下载 {image_count} 张图片，总大小: {total_download_size/1024/1024:.1f}MB")
    logging.info(f"总耗时: {total_time:.2f}秒，平均下载速度: {avg_speed:.2f}MB/s")
    logging.info(f"图片保存在目录：{base_dir}/")

if __name__ == "__main__":
    download_images_from_baidu("soil", 1000) 