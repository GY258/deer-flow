#!/bin/bash

# DeerFlow Nginx 反向代理配置脚本
# 使用方法: sudo ./setup-nginx.sh [http|https]

set -e

CONFIG_TYPE=${1:-http}
NGINX_CONFIG_FILE=""
NGINX_SITES_PATH="/etc/nginx/sites-available/deerflow"

echo "🚀 开始配置 DeerFlow Nginx 反向代理..."

# 检查是否以root权限运行
if [ "$EUID" -ne 0 ]; then
    echo "❌ 请使用 sudo 运行此脚本"
    exit 1
fi

# 检查nginx是否已安装
if ! command -v nginx &> /dev/null; then
    echo "📦 安装 Nginx..."
    apt update
    apt install -y nginx
fi

# 根据参数选择配置文件
if [ "$CONFIG_TYPE" = "https" ]; then
    NGINX_CONFIG_FILE="nginx-deerflow-https.conf"
    echo "🔒 使用 HTTPS 配置"
else
    NGINX_CONFIG_FILE="nginx-deerflow.conf"
    echo "🌐 使用 HTTP 配置"
fi

# 检查配置文件是否存在
if [ ! -f "$NGINX_CONFIG_FILE" ]; then
    echo "❌ 配置文件 $NGINX_CONFIG_FILE 不存在"
    exit 1
fi

# 复制配置文件到nginx目录
echo "📋 复制配置文件到 Nginx 目录..."
cp "$NGINX_CONFIG_FILE" "$NGINX_SITES_PATH"

# 启用站点
echo "🔗 启用 Nginx 站点..."
ln -sf "$NGINX_SITES_PATH" /etc/nginx/sites-enabled/

# 删除默认站点（如果存在）
if [ -f "/etc/nginx/sites-enabled/default" ]; then
    echo "🗑️  删除默认站点..."
    rm -f /etc/nginx/sites-enabled/default
fi

# 测试nginx配置
echo "🧪 测试 Nginx 配置..."
if nginx -t; then
    echo "✅ Nginx 配置测试通过"
else
    echo "❌ Nginx 配置测试失败"
    exit 1
fi

# 重载nginx
echo "🔄 重载 Nginx..."
systemctl reload nginx

# 检查nginx状态
echo "📊 检查 Nginx 状态..."
systemctl status nginx --no-pager

# 检查端口监听
echo "🔍 检查端口监听状态..."
netstat -tlnp | grep -E ':(80|443)' || echo "⚠️  端口80/443未监听，请检查防火墙设置"

echo ""
echo "🎉 Nginx 反向代理配置完成！"
echo ""
echo "📝 接下来的步骤："
echo "1. 确保域名 app.lerna-ai.com 解析到本服务器IP"
echo "2. 修改 docker-compose.yml 中的端口绑定"
echo "3. 更新 .env 文件中的 API URL"
echo "4. 重新部署 Docker 服务"
echo ""
echo "🔧 测试命令："
echo "curl -I http://app.lerna-ai.com"
echo "curl -I http://app.lerna-ai.com/api/config"
echo ""
echo "📋 配置文件位置："
echo "- Nginx配置: $NGINX_SITES_PATH"
echo "- 访问日志: /var/log/nginx/deerflow_access.log"
echo "- 错误日志: /var/log/nginx/deerflow_error.log"
