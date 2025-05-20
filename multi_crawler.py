import os
import time
import logging
from datetime import datetime
import threading
from queue import Queue
from concurrent.futures import ThreadPoolExecutor
import argparse
from baidu_crawler import download_images_from_baidu
from bing_crawler import crawl_bing_images

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
def setup_logging():
    """配置日志系统"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"logs/multi_crawler_{timestamp}.log"
    
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

def crawl_task(keyword, num_images, engine='baidu'):
    """单个爬虫任务"""
    try:
        logging.info(f"开始处理关键词: {keyword}, 搜索引擎: {engine}")
        if engine.lower() == 'baidu':
            download_images_from_baidu(keyword, num_images)
        elif engine.lower() == 'bing':
            crawl_bing_images(keyword, limit=num_images)
        else:
            logging.error(f"不支持的搜索引擎: {engine}")
    except Exception as e:
        logging.error(f"处理关键词 {keyword} 时发生错误: {e}")

def main():
    parser = argparse.ArgumentParser(description='多线程图片爬虫')
    parser.add_argument('--keywords', nargs='+', required=True, help='要搜索的关键词列表')
    parser.add_argument('--num_images', type=int, default=100, help='每个关键词要下载的图片数量')
    parser.add_argument('--max_workers', type=int, default=3, help='最大线程数')
    parser.add_argument('--engine', choices=['baidu', 'bing'], default='baidu', help='搜索引擎选择')
    
    args = parser.parse_args()
    
    # 创建必要的目录
    create_directories()
    
    # 设置日志
    setup_logging()
    
    start_time = time.time()
    logging.info(f"开始多线程爬虫任务")
    logging.info(f"关键词列表: {args.keywords}")
    logging.info(f"每个关键词图片数量: {args.num_images}")
    logging.info(f"最大线程数: {args.max_workers}")
    logging.info(f"搜索引擎: {args.engine}")
    
    # 使用线程池执行任务
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        # 提交所有任务
        futures = [
            executor.submit(crawl_task, keyword, args.num_images, args.engine)
            for keyword in args.keywords
        ]
        
        # 等待所有任务完成
        for future in futures:
            try:
                future.result()
            except Exception as e:
                logging.error(f"任务执行失败: {e}")
    
    total_time = time.time() - start_time
    logging.info(f"所有任务完成！总耗时: {total_time:.2f}秒")

if __name__ == "__main__":
    main() 