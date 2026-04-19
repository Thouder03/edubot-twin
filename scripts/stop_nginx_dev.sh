#!/bin/bash
sudo nginx -s stop 2>/dev/null && echo "[OK] Nginx 已停止" || echo "[INFO] Nginx 未在运行"
