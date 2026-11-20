# 阿里云部署与资料恢复

部署代码与日常开发代码使用同一 Git 仓库。服务器使用 Ubuntu 24.04、Docker Compose PostgreSQL 17/pgvector，以及 systemd 管理的 Python API。数据库仅绑定 127.0.0.1:5433，API 绑定 127.0.0.1:8080。

## 尚未备案时访问

使用 `deploy/nginx-search-private.conf`，Nginx 仅监听 127.0.0.1:8081。此配置保留为 SSH 隧道入口。

本机已配置 SSH 别名时：

```sh
ssh -N -L 127.0.0.1:8801:127.0.0.1:8081 dutch-corpus-server
```

然后访问 http://127.0.0.1:8801 。隧道关闭不影响服务器后台服务。域名上线仍需完成备案、域名解析、HTTPS 配置及公网验证。

经授权的临时 IPv4 预览使用 `deploy/nginx-search-public-ip.conf`，入口为 http://39.106.117.93/ （HTTP）。该配置与私有隧道入口并存，只开放 Nginx 的 80 端口，API 和数据库仍在回环地址监听。配置中的 `server_name` 必须随服务器 IPv4 更新；未知 Host 返回 404。入口保留 Nginx 和应用两层限流、原有模型累计预算限制。关闭临时预览时，移除对应 sites-enabled 链接并执行 `nginx -t && systemctl reload nginx`。

## 路径与密钥

- `/srv/dutch-corpus`：应用代码与 Python 虚拟环境。
- `/srv/dutch-corpus/deploy/search-engine.env`：运行密钥，root/search 可读，不提交 Git。
- `/var/lib/dutch-search/api-budget.sqlite3`：模型累计预算账本。迁移必须延续原账本，不能新建账本重置已用预算。
- `/srv/dutch-data/archive-20261120`：云端归档、数据库备份及容器恢复资料，仅 root 可读。
- 私有 OSS 保存独立备份，默认 AES256 加密并禁止公共访问。对象收据、SHA-256 与文件清单在本地 `local/migration-20261120` 留存。

不在 ECS 放置阿里云管理 AccessKey。归档下载使用本机生成的临时签名地址。

## 运维

```sh
systemctl status dutch-search nginx
journalctl -u dutch-search -n 80
cd /srv/dutch-corpus
docker compose --env-file /srv/dutch-data/migration/compose.env -f deploy/compose.yaml ps
curl http://127.0.0.1:8080/health
```

API 继续按来源 IP 限流，代理覆写 X-Forwarded-For，API 仅信任本机代理。私有 SSH 隧道阶段，不同测试者会共享服务器所见的本机 IP 配额。线上模型调用受持久化累计/每日预算约束；故障或预算耗尽时保留现有回退行为。

## 数据验证与恢复

`full-supabase.dump` 保留完整原始数据库备份；独立查询部署只恢复 public 业务 schema，先通过 `deploy/postgres-init.sql` 安装扩展与兼容角色，再运行 pg_restore。原 Supabase 数据卷冷备与 ARM64 镜像另行归档，不能直接用于 x86_64 ECS，应采用逻辑恢复。

迁移先核对 36 张 public 表的行数与内容 MD5，再设置 `deploy/search-db-permissions.sql` 的最小权限账号。SHA-256 校验用于核对归档本体；文件清单用于逐项核对解压后的资料。

`scripts/refresh_stale_embeddings.py` 默认仅预览。执行必须显式传 `--execute`，只处理标记 `stale:%` 的义项；相同文本哈希直接恢复索引版本，其余通过原有模型预算账本更新向量。不要用全量重建代替定向修复。

本地清理只针对已验证云端副本的项目资料与项目专属 Docker 卷。保留代码、Git、连接配置、校验收据；禁止全局 Docker prune 或删除共享 Docker 虚拟磁盘，以免影响其他项目。
