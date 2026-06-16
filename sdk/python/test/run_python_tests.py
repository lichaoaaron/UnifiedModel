#!/usr/bin/env python3
"""
MModel Python SDK 自动化测试脚本

这个脚本会自动完成以下流程：
1. 生成Python SDK
2. 运行完整测试
3. 运行演示程序
4. 生成测试报告
"""

import os
import sys
import subprocess
import time
import json
from pathlib import Path
from datetime import datetime


def run_command(cmd: str, description: str) -> tuple[bool, str]:
    """运行命令并返回结果"""
    print(f"🔄 {description}...")
    print(f"   命令: {cmd}")
    
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent
        )
        
        if result.returncode == 0:
            print(f"✅ {description}成功")
            return True, result.stdout
        else:
            print(f"❌ {description}失败")
            print(f"错误输出: {result.stderr}")
            return False, result.stderr
            
    except Exception as e:
        print(f"❌ {description}出现异常: {e}")
        return False, str(e)


def check_python_version():
    """检查Python版本"""
    print("🔍 检查Python版本...")
    version = sys.version_info
    
    if version.major < 3 or (version.major == 3 and version.minor < 7):
        print(f"❌ Python版本过低: {sys.version}")
        print("请使用Python 3.7或更高版本")
        return False
    
    print(f"✅ Python版本: {sys.version}")
    return True


def check_dependencies():
    """检查必要的依赖"""
    print("🔍 检查依赖...")
    
    required_modules = ['yaml', 'pathlib']
    missing_modules = []
    
    for module in required_modules:
        try:
            __import__(module)
            print(f"✅ {module}: 已安装")
        except ImportError:
            print(f"❌ {module}: 未安装")
            missing_modules.append(module)
    
    if missing_modules:
        print(f"请安装缺失的模块: pip install {' '.join(missing_modules)}")
        if 'yaml' in missing_modules:
            print("注意: yaml模块的包名是PyYAML")
        return False
    
    return True


def generate_python_sdk():
    """生成Python SDK"""
    generator_script = "scripts/generators/schema_python_generator_v2.py"
    
    if not Path(generator_script).exists():
        print(f"❌ 生成器脚本不存在: {generator_script}")
        return False
    
    success, output = run_command(
        f"python {generator_script}",
        "生成Python SDK"
    )
    
    if success:
        print("📋 生成器输出:")
        print(output)
    
    return success


def run_full_tests():
    """运行完整测试"""
    test_script = "scripts/test_python_sdk.py"
    
    if not Path(test_script).exists():
        print(f"❌ 测试脚本不存在: {test_script}")
        return False, ""
    
    success, output = run_command(
        f"python {test_script}",
        "运行完整测试"
    )
    
    return success, output


def run_demo():
    """运行演示程序"""
    demo_script = "scripts/demo_python_sdk.py"
    
    if not Path(demo_script).exists():
        print(f"❌ 演示脚本不存在: {demo_script}")
        return False, ""
    
    success, output = run_command(
        f"python {demo_script}",
        "运行演示程序"
    )
    
    return success, output


def generate_report(test_success: bool, test_output: str, demo_success: bool, demo_output: str):
    """生成测试报告"""
    print("📊 生成测试报告...")
    
    report = {
        "timestamp": datetime.now().isoformat(),
        "python_version": sys.version,
        "test_results": {
            "success": test_success,
            "output": test_output
        },
        "demo_results": {
            "success": demo_success,
            "output": demo_output
        },
        "summary": {
            "overall_success": test_success and demo_success,
            "test_passed": test_success,
            "demo_passed": demo_success
        }
    }
    
    # 保存到文件
    report_file = Path("test_report.json")
    try:
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"✅ 测试报告已保存到: {report_file}")
    except Exception as e:
        print(f"⚠️ 无法保存测试报告: {e}")
    
    return report


def print_summary(report: dict):
    """打印测试总结"""
    print("\n" + "=" * 60)
    print("📋 测试总结")
    print("=" * 60)
    
    print(f"测试时间: {report['timestamp']}")
    print(f"Python版本: {report['python_version'].split()[0]}")
    
    # 总体结果
    overall_success = report['summary']['overall_success']
    if overall_success:
        print("🎉 总体结果: 全部通过")
    else:
        print("⚠️ 总体结果: 存在失败")
    
    # 详细结果
    print(f"\n详细结果:")
    test_result = "✅ 通过" if report['summary']['test_passed'] else "❌ 失败"
    demo_result = "✅ 通过" if report['summary']['demo_passed'] else "❌ 失败"
    
    print(f"  完整测试: {test_result}")
    print(f"  演示程序: {demo_result}")
    
    # 建议
    print(f"\n📝 建议:")
    if overall_success:
        print("  - MModel Python SDK工作正常")
        print("  - 可以开始使用生成的SDK")
        print("  - 查看generated/python/mmodel/README.md了解更多用法")
    else:
        print("  - 检查错误输出，修复问题后重新运行")
        print("  - 确保schemas目录结构正确")
        print("  - 查看test_report.json获取详细信息")
    
    print("=" * 60)


def main():
    """主函数"""
    start_time = time.time()
    
    print("🚀 MModel Python SDK 自动化测试")
    print("=" * 60)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # 步骤1: 检查环境
    if not check_python_version():
        sys.exit(1)
    
    if not check_dependencies():
        print("\n💡 提示: 尝试安装依赖:")
        print("pip install PyYAML")
        sys.exit(1)
    
    print()
    
    # 步骤2: 生成SDK
    if not generate_python_sdk():
        print("❌ SDK生成失败，无法继续测试")
        sys.exit(1)
    
    print()
    
    # 步骤3: 运行测试
    test_success, test_output = run_full_tests()
    print()
    
    # 步骤4: 运行演示
    demo_success, demo_output = run_demo()
    print()
    
    # 步骤5: 生成报告
    report = generate_report(test_success, test_output, demo_success, demo_output)
    
    # 步骤6: 显示总结
    end_time = time.time()
    elapsed = end_time - start_time
    
    print(f"\n⏱️ 总耗时: {elapsed:.2f}秒")
    print_summary(report)
    
    # 设置退出代码
    if report['summary']['overall_success']:
        print("\n🎊 自动化测试完成！所有检查都通过了。")
        sys.exit(0)
    else:
        print("\n⚠️ 自动化测试完成，但存在问题。请检查上述错误信息。")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ 用户中断测试")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ 自动化测试出现异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1) 