# DeerFlow Nginx 反向代理部署指南

## 📁 创建的文件

我已经为你创建了以下文件：

1. **nginx-deerflow.conf** - HTTP版本的Nginx配置
2. **nginx-deerflow-https.conf** - HTTPS版本的Nginx配置  
3. **setup-nginx.sh** - 自动化配置脚本
4. **docker-compose-nginx.yml** - 适配Nginx的Docker配置

## 🚀 快速部署步骤

### 1. 配置Nginx反向代理

```bash
# 给脚本执行权限
chmod +x setup-nginx.sh

# 运行HTTP版本（推荐先测试）
sudo ./setup-nginx.sh http

# 或者运行HTTPS版本（需要SSL证书）
sudo ./setup-nginx.sh https
```

### 2. 更新Docker配置

```bash
# 备份原始配置
cp docker-compose.yml docker-compose.yml.backup

# 使用Nginx适配的配置
cp docker-compose-nginx.yml docker-compose.yml
```

### 3. 更新环境变量

在 `.env` 文件中添加或修改：

```bash
# CORS配置
ALLOWED_ORIGINS=http://app.lerna-ai.com,https://app.lerna-ai.com

# 前端API地址
NEXT_PUBLIC_API_URL=http://app.lerna-ai.com/api

# BM25服务地址
BM25_SERVER_URL=http://host.docker.internal:5003
```

### 4. 重新部署服务

```bash
# 停止现有服务
docker compose down

# 重新构建
docker compose build

# 启动服务
docker compose up -d

# 检查状态
docker compose ps
docker compose logs -f
```

## 🔧 手动配置步骤（如果脚本失败）

### 1. 安装Nginx

```bash
sudo apt update
sudo apt install -y nginx
```

### 2. 复制配置文件

```bash
# HTTP版本
sudo cp nginx-deerflow.conf /etc/nginx/sites-available/deerflow

# 或HTTPS版本
sudo cp nginx-deerflow-https.conf /etc/nginx/sites-available/deerflow
```

### 3. 启用站点

```bash
sudo ln -s /etc/nginx/sites-available/deerflow /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
```

### 4. 测试并重载

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## 🔍 验证部署

### 1. 检查服务状态

```bash
# 检查Nginx状态
sudo systemctl status nginx

# 检查Docker服务
docker compose ps

# 检查端口监听
sudo netstat -tlnp | grep -E ':(80|443|3000|8000)'
```

### 2. 测试访问

```bash
# 测试前端
curl -I http://app.lerna-ai.com

# 测试API
curl -I http://app.lerna-ai.com/api/config

# 测试CORS预检
curl -H "Origin: http://app.lerna-ai.com" \
     -H "Access-Control-Request-Method: POST" \
     -H "Access-Control-Request-Headers: Content-Type" \
     -X OPTIONS \
     http://app.lerna-ai.com/api/config
```

## 🔒 HTTPS配置（可选）

如果你有SSL证书，可以配置HTTPS：

### 1. 放置证书文件

```bash
# 创建证书目录
sudo mkdir -p /etc/ssl/certs /etc/ssl/private

# 复制证书文件（替换为你的实际证书）
sudo cp your-certificate.crt /etc/ssl/certs/app.lerna-ai.com.crt
sudo cp your-private-key.key /etc/ssl/private/app.lerna-ai.com.key

# 设置权限
sudo chmod 644 /etc/ssl/certs/app.lerna-ai.com.crt
sudo chmod 600 /etc/ssl/private/app.lerna-ai.com.key
```

### 2. 使用HTTPS配置

```bash
sudo cp nginx-deerflow-https.conf /etc/nginx/sites-available/deerflow
sudo nginx -t
sudo systemctl reload nginx
```

## 🛠️ 故障排除

### 1. 常见问题

- **502 Bad Gateway**: 检查Docker服务是否运行
- **CORS错误**: 检查ALLOWED_ORIGINS配置
- **端口冲突**: 检查端口是否被占用

### 2. 日志查看

```bash
# Nginx日志
sudo tail -f /var/log/nginx/deerflow_access.log
sudo tail -f /var/log/nginx/deerflow_error.log

# Docker日志
docker compose logs -f backend
docker compose logs -f frontend
```

### 3. 重启服务

```bash
# 重启Nginx
sudo systemctl restart nginx

# 重启Docker服务
docker compose restart
```

## 📊 性能优化

### 1. 启用Gzip压缩

在Nginx配置中添加：

```nginx
gzip on;
gzip_vary on;
gzip_min_length 1024;
gzip_types text/plain text/css text/xml text/javascript application/javascript application/xml+rss application/json;
```

### 2. 静态文件缓存

```nginx
location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg)$ {
    expires 1y;
    add_header Cache-Control "public, immutable";
}
```

## 🔐 安全建议

1. **防火墙配置**: 只开放必要端口
2. **SSL证书**: 使用有效的SSL证书
3. **定期更新**: 保持系统和软件更新
4. **访问控制**: 限制管理接口访问

## 📞 支持

如果遇到问题，请检查：

1. 域名解析是否正确
2. 防火墙是否开放端口
3. Docker服务是否正常运行
4. Nginx配置是否正确

完成这些步骤后，你的DeerFlow应用就可以通过 `http://app.lerna-ai.com` 正常访问了！

