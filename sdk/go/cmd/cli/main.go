package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"io/ioutil"
	"log"
	"os"
	"path/filepath"
	"strings"

	"mmodel_go_cli/mmodel"

	"gopkg.in/yaml.v3"
)

// CLI参数
var (
	inputFile    string
	outputFile   string
	inputFormat  string
	outputFormat string
	schemaType   string
	pretty       bool
	showHelp     bool
)

func init() {
	flag.StringVar(&inputFile, "i", "", "输入文件路径 (必需)")
	flag.StringVar(&inputFile, "input", "", "输入文件路径 (必需)")

	flag.StringVar(&outputFile, "o", "", "输出文件路径 (可选，默认输出到标准输出)")
	flag.StringVar(&outputFile, "output", "", "输出文件路径 (可选，默认输出到标准输出)")

	flag.StringVar(&inputFormat, "if", "", "输入格式: json, yaml (可选，默认根据文件扩展名自动检测)")
	flag.StringVar(&inputFormat, "input-format", "", "输入格式: json, yaml (可选，默认根据文件扩展名自动检测)")

	flag.StringVar(&outputFormat, "of", "json", "输出格式: json, yaml (默认: json)")
	flag.StringVar(&outputFormat, "output-format", "json", "输出格式: json, yaml (默认: json)")

	flag.StringVar(&schemaType, "t", "", "Schema类型: metric_set, entity_set, event_set, log_set, trace_set 等")
	flag.StringVar(&schemaType, "type", "", "Schema类型: metric_set, entity_set, event_set, log_set, trace_set 等")

	flag.BoolVar(&pretty, "p", true, "美化输出 (默认: true)")
	flag.BoolVar(&pretty, "pretty", true, "美化输出 (默认: true)")

	flag.BoolVar(&showHelp, "h", false, "显示帮助信息")
	flag.BoolVar(&showHelp, "help", false, "显示帮助信息")
}

func main() {
	flag.Parse()

	if showHelp || inputFile == "" {
		printUsage()
		if inputFile == "" && !showHelp {
			os.Exit(1)
		}
		return
	}

	// 读取输入文件
	data, err := ioutil.ReadFile(inputFile)
	if err != nil {
		log.Fatalf("无法读取文件 %s: %v", inputFile, err)
	}

	// 自动检测输入格式
	if inputFormat == "" {
		inputFormat = detectFormat(inputFile, data)
	}

	// 解析文件
	parsedData, err := parseFile(data, inputFormat, schemaType)
	if err != nil {
		log.Fatalf("解析失败: %v", err)
	}

	// 转换为目标格式
	output, err := convertToFormat(parsedData, outputFormat, pretty)
	if err != nil {
		log.Fatalf("转换格式失败: %v", err)
	}

	// 输出结果
	if outputFile != "" {
		err = ioutil.WriteFile(outputFile, output, 0644)
		if err != nil {
			log.Fatalf("写入文件失败: %v", err)
		}
		fmt.Printf("✅ 成功转换并保存到: %s\n", outputFile)

	} else {
		fmt.Print(string(output))
	}
}

func printUsage() {
	fmt.Println("MModel CLI - MModel文件格式转换工具")
	fmt.Println("\n用法:")
	fmt.Printf("  %s -i <输入文件> [选项]\n", os.Args[0])
	fmt.Println("\n选项:")
	fmt.Println("  -i, --input <文件>        输入文件路径 (必需)")
	fmt.Println("  -o, --output <文件>       输出文件路径 (可选，默认输出到标准输出)")
	fmt.Println("  -if, --input-format       输入格式: json, yaml (可选，默认自动检测)")
	fmt.Println("  -of, --output-format      输出格式: json, yaml (默认: json)")
	fmt.Println("  -t, --type                Schema类型 (可选，默认自动检测)")
	fmt.Println("  -p, --pretty              美化输出 (默认: true)")
	fmt.Println("  -h, --help                显示帮助信息")
	fmt.Println("\n支持的Schema类型:")
	fmt.Println("  - metric_set    指标集")
	fmt.Println("  - entity_set    实体集")
	fmt.Println("  - event_set     事件集")
	fmt.Println("  - log_set       日志集")
	fmt.Println("  - trace_set     追踪集")
	fmt.Println("  - data_link     数据链接")
	fmt.Println("  - storage_link  存储链接")
	fmt.Println("  - entity_set_link 实体集链接")
	fmt.Println("\n示例:")
	fmt.Printf("  # JSON转YAML\n")
	fmt.Printf("  %s -i metric.json -o metric.yaml -of yaml\n\n", os.Args[0])
	fmt.Printf("  # YAML转JSON (美化输出)\n")
	fmt.Printf("  %s -i entity.yaml -o entity.json\n\n", os.Args[0])
	fmt.Printf("  # 自动检测并输出到标准输出\n")
	fmt.Printf("  %s -i data.yaml -of json\n", os.Args[0])
}

func detectFormat(filename string, data []byte) string {
	// 先尝试根据文件扩展名判断
	ext := strings.ToLower(filepath.Ext(filename))
	switch ext {
	case ".json":
		return "json"
	case ".yaml", ".yml":
		return "yaml"
	}

	// 根据内容判断
	trimmed := strings.TrimSpace(string(data))
	if strings.HasPrefix(trimmed, "{") || strings.HasPrefix(trimmed, "[") {
		return "json"
	}
	return "yaml"
}

func parseFile(data []byte, format string, schemaType string) (interface{}, error) {

	var result mmodel.MModelCoreObject
	var err error

	// 解析数据
	switch format {
	case "json":
		result, err = mmodel.ParseJsonMModel(data)
		if err != nil {
			return nil, fmt.Errorf("JSON解析错误: %v", err)
		}
	case "yaml":
		result, err = mmodel.ParseYamlMModel(data)
		if err != nil {
			return nil, fmt.Errorf("YAML解析错误: %v", err)
		}
	default:
		return nil, fmt.Errorf("不支持的格式: %s", format)
	}

	fmt.Printf("📄 成功解析 %s 文件 (类型: %s)\n", format, schemaType)
	return result, nil
}

func convertToFormat(data interface{}, format string, pretty bool) ([]byte, error) {
	switch format {
	case "json":
		if pretty {
			return json.MarshalIndent(data, "", "  ")
		}
		return json.Marshal(data)
	case "yaml":
		return yaml.Marshal(data)
	default:
		return nil, fmt.Errorf("不支持的输出格式: %s", format)
	}
}
