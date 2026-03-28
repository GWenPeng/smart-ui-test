-- NL Test Framework Database Schema

CREATE DATABASE IF NOT EXISTS nl_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE nl_test;

-- 测试用例
CREATE TABLE IF NOT EXISTS test_cases (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL COMMENT '测试用例名称',
    description TEXT COMMENT '描述',
    target_url VARCHAR(2048) NOT NULL COMMENT '目标URL',
    natural_input TEXT NOT NULL COMMENT '原始自然语言输入',
    status ENUM('draft', 'ready', 'archived') DEFAULT 'draft',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='测试用例表';

-- 测试步骤
CREATE TABLE IF NOT EXISTS test_steps (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_id BIGINT NOT NULL,
    step_order INT NOT NULL COMMENT '步骤顺序',
    action VARCHAR(50) NOT NULL COMMENT '动作类型',
    target TEXT NOT NULL COMMENT '目标元素描述',
    value VARCHAR(2048) DEFAULT NULL COMMENT '输入值',
    locator_strategy VARCHAR(50) DEFAULT NULL COMMENT '定位策略',
    locator_value TEXT DEFAULT NULL COMMENT '定位表达式',
    iframe_hint VARCHAR(255) DEFAULT NULL COMMENT 'iframe提示',
    timeout_ms INT DEFAULT 10000 COMMENT '超时毫秒',
    raw_text TEXT COMMENT '原始自然语言',
    status ENUM('pending', 'generated', 'confirmed') DEFAULT 'pending',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (case_id) REFERENCES test_cases(id) ON DELETE CASCADE,
    INDEX idx_case_order (case_id, step_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='测试步骤表';

-- 测试运行记录
CREATE TABLE IF NOT EXISTS test_runs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_id BIGINT NOT NULL,
    status ENUM('queued', 'running', 'passed', 'failed', 'error') DEFAULT 'queued',
    started_at DATETIME DEFAULT NULL,
    finished_at DATETIME DEFAULT NULL,
    duration_ms INT DEFAULT NULL COMMENT '总耗时毫秒',
    error_message TEXT DEFAULT NULL,
    browser_info VARCHAR(255) DEFAULT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (case_id) REFERENCES test_cases(id) ON DELETE CASCADE,
    INDEX idx_status (status),
    INDEX idx_case (case_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='测试运行记录表';

-- 步骤执行结果
CREATE TABLE IF NOT EXISTS step_results (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id BIGINT NOT NULL,
    step_id BIGINT NOT NULL,
    step_order INT NOT NULL,
    status ENUM('passed', 'failed', 'skipped') NOT NULL,
    duration_ms INT DEFAULT NULL,
    error_message TEXT DEFAULT NULL,
    screenshot_path VARCHAR(512) DEFAULT NULL,
    iframe_path JSON DEFAULT NULL COMMENT 'iframe遍历路径',
    element_info JSON DEFAULT NULL COMMENT '定位到的元素信息',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES test_runs(id) ON DELETE CASCADE,
    FOREIGN KEY (step_id) REFERENCES test_steps(id) ON DELETE CASCADE,
    INDEX idx_run (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='步骤执行结果表';

-- iframe 缓存表 - 缓存页面iframe结构
CREATE TABLE IF NOT EXISTS iframe_cache (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    url_pattern VARCHAR(512) NOT NULL COMMENT 'URL匹配模式',
    iframe_tree JSON NOT NULL COMMENT 'iframe层级结构',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_url (url_pattern)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='iframe结构缓存表';
