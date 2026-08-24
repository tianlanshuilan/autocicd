"""
阿里云效 DevOps API 客户端

提供对云效流水线的自动化控制能力：
- 创建项目
- 创建流水线
- 配置构建和部署步骤
- 设置触发规则

认证方式：阿里云 AccessKey ID + AccessKey Secret
"""

from alibabacloud_devops20210625.client import Client
from alibabacloud_devops20210625 import models as devops_models
from alibabacloud_tea_openapi import models as open_api_models
from typing import Optional, Dict, Any
import json


class AliyunDevOpsError(Exception):
    """云效 API 错误"""
    pass


class AliyunDevOpsClient:
    """阿里云效 DevOps API 客户端"""
    
    def __init__(self, access_key_id: str, access_key_secret: str, region_id: str = "cn_hangzhou"):
        """
        初始化云效客户端
        
        Args:
            access_key_id: 阿里云 AccessKey ID
            access_key_secret: 阿里云 AccessKey Secret
            region_id: 区域 ID（默认 cn_hangzhou）
        """
        self.access_key_id = access_key_id
        self.access_key_secret = access_key_secret
        self.region_id = region_id
        self.client = None
        self._init_client()
    
    def _init_client(self):
        """初始化 API 客户端"""
        try:
            config = open_api_models.Config(
                access_key_id=self.access_key_id,
                access_key_secret=self.access_key_secret,
            )
            config.endpoint = f'devops.{self.region_id}.aliyuncs.com'
            self.client = Client(config)
        except Exception as e:
            raise AliyunDevOpsError(f"初始化云效客户端失败: {str(e)}")
    
    def create_project(self, name: str, description: str = "", organization_id: str = "") -> Dict[str, Any]:
        """
        创建云效项目
        
        Args:
            name: 项目名称
            description: 项目描述
            organization_id: 组织 ID（可选）
            
        Returns:
            项目信息字典
        """
        try:
            request = devops_models.CreateProjectRequest(
                name=name,
                description=description,
            )
            if organization_id:
                request.organization_id = organization_id
            
            response = self.client.create_project(request)
            
            if response.status_code != 200:
                raise AliyunDevOpsError(f"创建项目失败: HTTP {response.status_code}")
            
            return {
                "project_id": response.body.project_id,
                "name": name,
                "url": f"https://devops.aliyun.com/project/{response.body.project_id}"
            }
        except Exception as e:
            raise AliyunDevOpsError(f"创建项目失败: {str(e)}")
    
    def create_pipeline(
        self,
        project_id: str,
        name: str,
        service_connection_id: str,
        repo_url: str,
        branch: str = "main",
        pipeline_config: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        创建流水线
        
        Args:
            project_id: 项目 ID
            name: 流水线名称
            service_connection_id: 服务连接 ID（代码源）
            repo_url: 仓库地址
            branch: 默认分支
            pipeline_config: 流水线配置（可选，使用默认配置）
            
        Returns:
            流水线信息字典
        """
        try:
            # 构建流水线配置
            if pipeline_config is None:
                pipeline_config = self._build_default_pipeline_config(
                    service_connection_id, repo_url, branch
                )
            
            request = devops_models.CreatePipelineRequest(
                project_id=project_id,
                name=name,
                pipeline_config=json.dumps(pipeline_config),
            )
            
            response = self.client.create_pipeline(request)
            
            if response.status_code != 200:
                raise AliyunDevOpsError(f"创建流水线失败: HTTP {response.status_code}")
            
            return {
                "pipeline_id": response.body.pipeline_id,
                "name": name,
                "url": f"https://devops.aliyun.com/pipeline/{response.body.pipeline_id}"
            }
        except Exception as e:
            raise AliyunDevOpsError(f"创建流水线失败: {str(e)}")
    
    def _build_default_pipeline_config(
        self,
        service_connection_id: str,
        repo_url: str,
        branch: str
    ) -> Dict[str, Any]:
        """
        构建默认流水线配置
        
        Args:
            service_connection_id: 服务连接 ID
            repo_url: 仓库地址
            branch: 分支
            
        Returns:
            流水线配置字典
        """
        return {
            "sources": [
                {
                    "type": "codeup",
                    "name": "代码源",
                    "service_connection_id": service_connection_id,
                    "repo": repo_url,
                    "branch": branch,
                }
            ],
            "stages": [
                {
                    "name": "构建",
                    "jobs": [
                        {
                            "name": "构建任务",
                            "taskType": "build",
                            "steps": [
                                {
                                    "name": "代码检出",
                                    "type": "checkout"
                                },
                                {
                                    "name": "构建",
                                    "type": "shell",
                                    "script": "echo 'Build step'"
                                }
                            ]
                        }
                    ]
                }
            ],
            "triggers": [
                {
                    "type": "push",
                    "branches": [branch]
                }
            ]
        }
    
    def create_service_connection(
        self,
        project_id: str,
        name: str,
        connection_type: str,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        创建服务连接（代码源、部署目标等）
        
        Args:
            project_id: 项目 ID
            name: 连接名称
            connection_type: 连接类型（codeup/github/gitlab等）
            config: 连接配置
            
        Returns:
            服务连接信息字典
        """
        try:
            request = devops_models.CreateServiceConnectionRequest(
                project_id=project_id,
                name=name,
                connection_type=connection_type,
                config=json.dumps(config),
            )
            
            response = self.client.create_service_connection(request)
            
            if response.status_code != 200:
                raise AliyunDevOpsError(f"创建服务连接失败: HTTP {response.status_code}")
            
            return {
                "connection_id": response.body.service_connection_id,
                "name": name,
                "type": connection_type
            }
        except Exception as e:
            raise AliyunDevOpsError(f"创建服务连接失败: {str(e)}")
    
    def get_pipeline(self, pipeline_id: str) -> Dict[str, Any]:
        """
        获取流水线详情
        
        Args:
            pipeline_id: 流水线 ID
            
        Returns:
            流水线信息字典
        """
        try:
            request = devops_models.GetPipelineRequest(pipeline_id=pipeline_id)
            response = self.client.get_pipeline(request)
            
            if response.status_code != 200:
                raise AliyunDevOpsError(f"获取流水线失败: HTTP {response.status_code}")
            
            return {
                "pipeline_id": response.body.pipeline_id,
                "name": response.body.name,
                "status": response.body.status,
                "url": f"https://devops.aliyun.com/pipeline/{pipeline_id}"
            }
        except Exception as e:
            raise AliyunDevOpsError(f"获取流水线失败: {str(e)}")
    
    def run_pipeline(self, pipeline_id: str, branch: Optional[str] = None) -> Dict[str, Any]:
        """
        触发流水线运行
        
        Args:
            pipeline_id: 流水线 ID
            branch: 分支（可选，使用默认分支）
            
        Returns:
            运行信息字典
        """
        try:
            request = devops_models.RunPipelineRequest(pipeline_id=pipeline_id)
            if branch:
                request.branch = branch
            
            response = self.client.run_pipeline(request)
            
            if response.status_code != 200:
                raise AliyunDevOpsError(f"触发流水线失败: HTTP {response.status_code}")
            
            return {
                "run_id": response.body.pipeline_run_id,
                "pipeline_id": pipeline_id,
                "status": "running"
            }
        except Exception as e:
            raise AliyunDevOpsError(f"触发流水线失败: {str(e)}")
