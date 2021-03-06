#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
author by jacksyen[hyqiu.syen@gmail.com]
---------------------------------------
celery异步任务
server:
    #[root用户运行]
    export C_FORCE_ROOT='true'
    celery -A util.tasks worker -l info
"""
import time
import json
import requests

from celery import Task
from celery import Celery,platforms

from util.log import logger
from util.util import ImageUtil
from util.mail import SendMail
from db.dbase import Database
import globals

# 强制root执行
platforms.C_FORCE_ROOT = True

app = Celery()
# 加载celery配置文件
app.conf.enable_utc = True
app.conf.timezone = 'Asia/Shanghai'
app.conf.broker_url = globals.BROKER_URL
app.conf.result_backend = "amqp"
app.conf.result_expires = globals.CELERY_TASK_RESULT_EXPIRES


class BaseTask(Task):

    abstract = True

    def after_return(self, *args, **kwargs):
        pass

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        try:
            logger.error(u'发送邮件失败，celery task id: %s, 参数:%s, 错误信息：%s' %(task_id, str(args), str(exc)))
            db = Database()
            db.email_update_status(str(args[0]), globals.STATUS.get('error'))
        except Exception as e:
            logger.error(u'更新发送邮件状态异常，错误:%s,参数:%s' %(str(e), str(args)))

    def on_retry(self, *args, **kwargs):
        pass

    def on_success(self, retval, task_id, args, kwargs):
        try:
            logger.info(u'发送邮件成功，参数:%s' %str(args))
            # 更新发送邮件状态
            db = Database()
            db.email_update_status(str(args[0]), globals.STATUS.get('complete'))
        except Exception as e:
            logger.error(u'更新发送邮件状态异常，错误:%s,参数:%s' %(str(e), str(args)))

'''
API base task
'''
class ApiBaseTask(Task):

    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(u'调用API接口失败，celery task id:%s, 参数:%s, 错误信息:%s' %(task_id, str(args), str(exc)))

'''
Download base task
'''
class DownloadBaseTask(Task):

    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(u'下载文件失败，celery task id:%s，参数:%s，错误信息：%s' %(task_id, str(args), str(exc)))

'''
调用API接口
'''
class ApiTask(object):

    @app.task(base=ApiBaseTask, max_retries=3)
    def post(url, params):
        try:
            result = requests.post(url, params, timeout=globals.HTTP_TIME_OUT)
            if not result:
                ApiTask.post.retry(countdown=20, exc=e)
                return
            result = result.json
            if str(json_result.get('status')) != globals.API_STATUS.get('success'):
                ApiTask.post.retry(countdown=20, exc=e)
                return
        except Exception as e:
            # 延迟20s重试
            ApiTask.post.retry(countdown=20, exc=e)
        return json_result


'''
发送邮件任务
'''
class MailTask(object):

    '''
    发送邮件,发送失败后间隔30秒重新发送
    重试次数：5
    mail_id: 邮件ID
    attach_file: 附件文件路径
    to_email: 收件方
    title: 邮件标题
    auth: 邮件作者
    '''
    @app.task(base=BaseTask, max_retries=3)
    def send(mail_id, attach_file, to_email, title, auth):
        try:
            mail = SendMail()
            # 发送邮件
            mail.send(attach_file, to_email, title, auth)
        except Exception as err:
            ## 延迟30s后重试
            MailTask.send.retry(countdown=30, exc=err)

'''
下载任务队列
'''
class DownloadTask(object):

    '''
    调用：DownloadTask.get_image.delay(<url>, <file_dir>)
    最大重试次数：5
    url: 下载URL
    file_dir: 文件本地存储目录
    '''
    @app.task(base=DownloadBaseTask, max_retries=3)
    def get_image(url, file_dir):
        try:
            time.sleep(0.5)
            data = requests.get(url, timeout=globals.HTTP_TIME_OUT, headers=globals.HEADERS)
            # 文件路径
            file_path = '%s/%s' %(file_dir, url[url.rfind('/')+1:])
            with open(file_path, 'wb') as f_data:
                f_data.write(data.content)
                f_data.close()
                # 压缩
                ImageUtil.compress(file_path, globals.PIC_MAX_WIDTH)
        except Exception as e:
            ## 延迟20s后重试
            DownloadTask.get_image.retry(countdown=20, exc=e)
        return file_path
