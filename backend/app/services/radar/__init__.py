"""研究雷达订阅（Research Radar Subscription）子系统。

生克隔离核心：`subscription_store`（零 PII，subscriptions.db）与后续的
`contact_store`（隔离 + 加密，contacts.db）分文件、无外键、无交叉索引。
"""
