"""商用权利声明的解析与拦截。

这一层是产品的法律底线，不是表单校验。核心原则：

* **缺省即拒绝。** 字段缺失、写 "unknown"、写 "待确认"，一律当作未授权。
  绝不把"没说不行"读成"行"。
* **不可用免责声明代替处理。** 声明里写"如有侵权请联系删除"不构成授权。
* **可识别人物单独确认。** 拥有照片著作权 ≠ 拥有画面里人物的肖像商用权，
  这是两件事，必须分别声明。

装配器在权利未确认时 **不产出任何印刷文件**，只产出一份说明拒绝原因的报告。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

#: 视为"明确肯定"的取值。刻意不接受 "unknown" / "n/a" / "待确认" / 空串。
TRUE_WORDS = {"yes", "true", "y", "1", "confirmed", "是", "已确认", "有"}
FALSE_WORDS = {"no", "false", "n", "0", "否", "无", "没有"}

#: 必须逐项明确回答的问题
REQUIRED_FIELDS = {
    "owns_photo_copyright":
        "用户是否拥有这张照片本身的著作权（自己拍摄或已获转让）",
    "commercial_use_granted":
        "用户是否确认该照片可用于商业用途",
    "identifiable_people":
        "画面中是否存在可识别的人物",
    "third_party_ip":
        "画面中是否包含商标 / 品牌 / 版权角色 / 受保护的艺术品或建筑",
}

#: 条件必答：只有当上面对应项为"是"时才需要
CONDITIONAL_FIELDS = {
    "identifiable_people": ("portrait_release", "可识别人物的肖像商用授权是否已取得"),
    "third_party_ip": ("ip_license", "第三方 IP 的商用许可是否已取得"),
}


class RightsError(ValueError):
    """权利声明不完整或不足以支撑商业交付。"""


def _tri(value) -> bool | None:
    """把声明值收敛成 True / False / None（None = 未明确回答）。"""
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    s = str(value).strip().lower()
    if s in TRUE_WORDS:
        return True
    if s in FALSE_WORDS:
        return False
    return None


@dataclass
class Rights:
    raw: Dict
    declared_by: str = ""
    declared_at: str = ""
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.blockers

    def to_dict(self) -> dict:
        return {
            "declared_by": self.declared_by,
            "declared_at": self.declared_at,
            "cleared_for_commercial_use": self.ok,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "raw": self.raw,
        }

    def require_ok(self) -> None:
        if not self.ok:
            raise RightsError(
                "商用权利未确认，拒绝产出印刷文件：\n  - "
                + "\n  - ".join(self.blockers))


def evaluate(raw: Dict) -> Rights:
    """把一份声明 dict 评估成放行 / 拦截。"""
    r = Rights(raw=dict(raw),
               declared_by=str(raw.get("declared_by", "") or ""),
               declared_at=str(raw.get("declared_at", "") or ""))

    if not r.declared_by:
        r.blockers.append("declared_by 缺失：必须记录是谁做出的权利声明")

    answers: Dict[str, bool | None] = {}
    for key, question in REQUIRED_FIELDS.items():
        v = _tri(raw.get(key))
        answers[key] = v
        if v is None:
            r.blockers.append(f"{key} 未明确回答（{question}）；未回答一律按未授权处理")

    if answers.get("owns_photo_copyright") is False:
        r.blockers.append("owns_photo_copyright=否：用户不拥有照片著作权，不能进入商业生产")
    if answers.get("commercial_use_granted") is False:
        r.blockers.append("commercial_use_granted=否：用户未授权商业使用")

    for trigger, (dep_key, question) in CONDITIONAL_FIELDS.items():
        if answers.get(trigger) is True:
            dep = _tri(raw.get(dep_key))
            if dep is None:
                r.blockers.append(
                    f"{trigger}=是，但 {dep_key} 未回答（{question}）")
            elif dep is False:
                r.blockers.append(
                    f"{trigger}=是且 {dep_key}=否：缺少必要授权。"
                    f"请改做不含该元素的保守版本，或补齐授权后重跑")
            else:
                r.warnings.append(
                    f"{dep_key}=是：已声明取得授权，交付报告会标注"
                    f"「依赖用户声明，未经法律审查」")

    if answers.get("identifiable_people") is False:
        r.warnings.append("声明无可识别人物：成品复检仍需确认没有意外入镜的路人")

    return r


def load_rights(path) -> Rights:
    p = Path(path)
    if not p.exists():
        raise RightsError(
            f"缺少权利声明文件：{p}\n"
            f"必答字段：{', '.join(REQUIRED_FIELDS)}\n"
            f"参考模板见 docs/ARTWORK_CONTRACT.md")
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RightsError(f"权利声明不是合法 JSON：{p}（{exc}）") from exc
    if not isinstance(raw, dict):
        raise RightsError(f"权利声明顶层必须是对象：{p}")
    return evaluate(raw)


TEMPLATE = {
    "declared_by": "客户姓名或订单联系人",
    "declared_at": "2026-09-10",
    "owns_photo_copyright": "yes",
    "commercial_use_granted": "yes",
    "identifiable_people": "no",
    "portrait_release": "n/a",
    "third_party_ip": "no",
    "ip_license": "n/a",
    "notes": "补充说明：照片拍摄场景、是否有其他需要注意的元素",
}


__all__ = ["Rights", "RightsError", "load_rights", "evaluate",
           "REQUIRED_FIELDS", "CONDITIONAL_FIELDS", "TEMPLATE"]
