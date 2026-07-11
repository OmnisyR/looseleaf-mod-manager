"""Human-readable metadata for model info sections and fields (zh_CN).

Labels reuse the wording already established in the mod manager's preview
panel; help texts and slider ranges are MI Studio additions. Meanings marked
（推测）are inferred from observed data, not official documentation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SectionInfo:
    label: str
    help: str


SECTION_INFO: dict[str, SectionInfo] = {
    "Bounding": SectionInfo("包围盒", "模型整体的包围盒，用于镜头裁剪、遮挡计算等。size 为尺寸，offset 为中心偏移。"),
    "Collider": SectionInfo("碰撞体", "模型与场景/角色交互用的碰撞形状。"),
    "SpecificCollider": SectionInfo("专用碰撞体", "供动态骨骼单独引用的碰撞体列表（按名称引用 need_specific 的碰撞体）。"),
    "DynamicBone": SectionInfo(
        "动态骨骼（物理）",
        "头发、裙摆、胸部、饰品等的摇动物理。每个条目是一条骨骼链（Joint 列表，"
        "从根到末端），常见修改：阻尼、重力、回弹、旋转限制、碰撞半径。",
    ),
    "DynamicBoneCollider": SectionInfo(
        "动态骨骼碰撞体",
        "与动态骨骼交互、防止穿模的碰撞体（多为球/胶囊）。挂在指定骨骼(node)上，"
        "param0 通常为半径，offset 为相对骨骼的偏移。",
    ),
    "NeighborBones": SectionInfo("相邻骨骼", "动态骨骼链之间的关联约束，让相邻链条一起摆动（如裙摆相邻布片）。"),
    "LookIK": SectionInfo("视线 IK", "注视目标时头部/脊柱的自动旋转。每个 Joint 定义参与的骨骼与旋转限制。"),
    "TwoBoneIK": SectionInfo("双骨骼 IK", "手臂/腿部的两段式 IK（如脚贴地面）。root/middle/top 为三个关节。"),
    "Locators": SectionInfo("挂点", "特效、武器、道具等的附着点。node 为绑定骨骼，offset/rot 为相对位置与旋转。"),
    "Lights": SectionInfo("灯光", "模型自带的灯光定义。"),
    "LOD": SectionInfo("LOD", "多级细节切换设置。"),
    "Occluder": SectionInfo("遮挡体", "该模型是否作为遮挡体参与遮挡剔除。"),
    "Extra": SectionInfo("额外参数", "杂项参数（如 door_type 门类型）。"),
    "Animation": SectionInfo("动画", "动画相关设置。"),
    "DrivenKeys": SectionInfo("驱动关键帧", "由某属性驱动另一属性的关键帧曲线（如表情联动）。"),
    "Drivers": SectionInfo("驱动器", "驱动关键帧的输入定义。"),
    "Keys": SectionInfo("关键帧", "驱动曲线上的关键帧点。"),
    "TwoBoneIk": SectionInfo("双骨骼 IK", "手臂/腿部的两段式 IK。"),
}


@dataclass(frozen=True)
class FieldInfo:
    label: str
    help: str
    # Slider range for numeric fields; None disables the slider.
    range: tuple[float, float] | None = None
    integer: bool = False


_ANGLE = (-3.14159, 3.14159)
_ANGLE_POS = (0.0, 3.14159)
_UNIT = (0.0, 1.0)
_OFFSET = (-1.0, 1.0)

FIELD_INFO: dict[str, FieldInfo] = {
    # -- DynamicBone joints ------------------------------------------------
    "damping": FieldInfo("阻尼", "抑制摆动的力度，越大摆动衰减越快、越“稳”。常用 0~1。", _UNIT),
    "damping_min": FieldInfo("最小阻尼", "开启动态阻尼(is_dynamic_damping)时，低速状态下使用的阻尼下限。", _UNIT),
    "damping_max": FieldInfo("最大阻尼", "开启动态阻尼(is_dynamic_damping)时，高速状态下使用的阻尼上限。", _UNIT),
    "damping_velocity_ratio": FieldInfo("速度阻尼比", "动态阻尼对速度的敏感程度，越大越容易达到最大阻尼（推测）。", _UNIT),
    "is_dynamic_damping": FieldInfo("动态阻尼", "开启后阻尼随运动速度在最小/最大阻尼之间变化。"),
    "gravity": FieldInfo("重力", "负值向下拉，绝对值越大越下垂；0 表示不受重力。", (-2.0, 2.0)),
    "resilience": FieldInfo("回弹", "拉回原始姿态的力度，越大越硬、回位越快。", (0.0, 50.0)),
    "rotation_limit": FieldInfo("旋转限制", "相对初始姿态允许摆动的最大角度（弧度），π≈3.14 约等于不限制。", _ANGLE_POS),
    "stretch_limit": FieldInfo("拉伸限制", "骨骼允许拉伸的比例上限，0 为禁止拉伸。", (0.0, 2.0)),
    "stretch_resilience": FieldInfo("拉伸回弹", "拉伸后恢复原长的力度。", (0.0, 50.0)),
    "is_enable_stretch": FieldInfo("允许拉伸", "是否允许该骨骼被拉伸。"),
    "wind_influence": FieldInfo("风影响", "受场景风力影响的倍率，0 为不受风。", (0.0, 2.0)),
    "collision_radius": FieldInfo("碰撞半径", "该骨骼参与碰撞的球体半径（米），0 为不参与碰撞。", (0.0, 0.5)),
    "freeze_axis": FieldInfo("冻结轴", "限制运动的轴向：0=不冻结，1/2/3 对应 X/Y/Z 平面（推测）。", (0, 3), integer=True),
    "driven_infl": FieldInfo("驱动影响", "受驱动动画影响的权重（推测）。", _UNIT),
    "is_disable": FieldInfo("禁用", "勾选后该骨骼的物理模拟被禁用。"),
    "ignore_collision": FieldInfo("忽略碰撞", "该骨骼链不与任何碰撞体交互。"),
    "node": FieldInfo("骨骼节点", "绑定的骨骼名称，需存在于模型骨架中。"),
    # -- DynamicBoneCollider ----------------------------------------------
    "name": FieldInfo("名称", "该条目的标识名称。"),
    "type": FieldInfo("类型", "形状/行为类型编号（碰撞体常见 0=球，1=胶囊，2=平面，推测）。", (0, 4), integer=True),
    "need_specific": FieldInfo("仅供指定引用", "开启后仅被 SpecificCollider 显式引用的骨骼使用（推测）。"),
    "param0": FieldInfo("参数0", "主要尺寸：球/胶囊半径（推测，随类型而异）。", (0.0, 1.0)),
    "param1": FieldInfo("参数1", "次要尺寸：胶囊长度/高度（推测，随类型而异）。", (0.0, 1.0)),
    "param2": FieldInfo("参数2", "含义随类型而异（推测）。", (0.0, 1.0)),
    "param3": FieldInfo("参数3", "含义随类型而异（推测）。", (0.0, 1.0)),
    "offset_x": FieldInfo("偏移 X", "相对绑定骨骼的位置偏移（米）。", _OFFSET),
    "offset_y": FieldInfo("偏移 Y", "相对绑定骨骼的位置偏移（米）。", _OFFSET),
    "offset_z": FieldInfo("偏移 Z", "相对绑定骨骼的位置偏移（米）。", _OFFSET),
    "offset_rot_x": FieldInfo("旋转偏移 X", "相对绑定骨骼的旋转（弧度）。", _ANGLE),
    "offset_rot_y": FieldInfo("旋转偏移 Y", "相对绑定骨骼的旋转（弧度）。", _ANGLE),
    "offset_rot_z": FieldInfo("旋转偏移 Z", "相对绑定骨骼的旋转（弧度）。", _ANGLE),
    # -- Locators -----------------------------------------------------------
    "off_x": FieldInfo("位置 X", "相对参考点的位置偏移（米）。", _OFFSET),
    "off_y": FieldInfo("位置 Y", "相对参考点的位置偏移（米）。", _OFFSET),
    "off_z": FieldInfo("位置 Z", "相对参考点的位置偏移（米）。", _OFFSET),
    "rot_x": FieldInfo("旋转 X", "旋转角（弧度）。", _ANGLE),
    "rot_y": FieldInfo("旋转 Y", "旋转角（弧度）。", _ANGLE),
    "rot_z": FieldInfo("旋转 Z", "旋转角（弧度）。", _ANGLE),
    # -- LookIK ---------------------------------------------------------------
    "look_offset_x": FieldInfo("视线偏移 X", "注视点的偏移量（米）。", _OFFSET),
    "look_offset_y": FieldInfo("视线偏移 Y", "注视点的偏移量（米）。", _OFFSET),
    "look_offset_z": FieldInfo("视线偏移 Z", "注视点的偏移量（米）。", _OFFSET),
    "up_vec_x": FieldInfo("上方向 X", "IK 求解使用的上方向向量分量。", _OFFSET),
    "up_vec_y": FieldInfo("上方向 Y", "IK 求解使用的上方向向量分量。", _OFFSET),
    "up_vec_z": FieldInfo("上方向 Z", "IK 求解使用的上方向向量分量。", _OFFSET),
    "rx_limit_max": FieldInfo("X 旋转上限", "该关节绕 X 轴（俯仰）允许的最大角度（弧度）。", _ANGLE),
    "rx_limit_min": FieldInfo("X 旋转下限", "该关节绕 X 轴（俯仰）允许的最小角度（弧度）。", _ANGLE),
    "ry_limit_max": FieldInfo("Y 旋转上限", "该关节绕 Y 轴（左右）允许的最大角度（弧度）。", _ANGLE),
    "ry_limit_min": FieldInfo("Y 旋转下限", "该关节绕 Y 轴（左右）允许的最小角度（弧度）。", _ANGLE),
    "axis_x": FieldInfo("轴向 X", "IK 弯曲轴向量分量。", _OFFSET),
    "axis_y": FieldInfo("轴向 Y", "IK 弯曲轴向量分量。", _OFFSET),
    "axis_z": FieldInfo("轴向 Z", "IK 弯曲轴向量分量。", _OFFSET),
    # -- TwoBoneIK -----------------------------------------------------------
    "root": FieldInfo("根关节", "IK 链的根关节骨骼名（如大腿/上臂）。"),
    "middle": FieldInfo("中间关节", "IK 链的中间关节骨骼名（如膝盖/手肘）。"),
    "top": FieldInfo("末端关节", "IK 链的末端骨骼名（如脚/手）。"),
    "omit_middle": FieldInfo("忽略中间关节", "求解时不旋转中间关节（推测）。"),
    "length_limit": FieldInfo("长度限制", "IK 链的伸展长度限制比例。", (0.0, 2.0)),
    "root_rot_max": FieldInfo("根部最大旋转", "根关节允许的最大旋转（弧度）。", _ANGLE),
    "root_rot_min": FieldInfo("根部最小旋转", "根关节允许的最小旋转（弧度）。", _ANGLE),
    "mid_rot_max": FieldInfo("中段最大旋转", "中间关节允许的最大旋转（弧度）。", _ANGLE),
    "mid_rot_min": FieldInfo("中段最小旋转", "中间关节允许的最小旋转（弧度）。", _ANGLE),
    # -- Bounding / Occluder / Extra ------------------------------------------
    "size": FieldInfo("尺寸", "包围盒尺寸（米）。"),
    "offset": FieldInfo("偏移", "包围盒中心相对模型原点的偏移（米）。"),
    "x": FieldInfo("X", "X 分量。", (-5.0, 5.0)),
    "y": FieldInfo("Y", "Y 分量。", (-5.0, 5.0)),
    "z": FieldInfo("Z", "Z 分量。", (-5.0, 5.0)),
    "is_valid": FieldInfo("启用", "是否启用。"),
    "door_type": FieldInfo("门类型", "门对象的行为类型编号。", (0, 10), integer=True),
    # -- Animation / DrivenKeys ------------------------------------------------
    "attr": FieldInfo("属性", "被驱动的属性名。"),
    "driven": FieldInfo("被驱动对象", "被驱动的节点名。"),
    "driven_attr": FieldInfo("被驱动属性", "被驱动对象上的属性名。"),
    "target": FieldInfo("目标", "目标节点/对象名。"),
    "blend": FieldInfo("混合", "混合权重。", _UNIT),
    "interp": FieldInfo("插值", "插值方式编号。", (0, 4), integer=True),
    "time": FieldInfo("时间", "关键帧时间。"),
    "value": FieldInfo("数值", "关键帧数值。"),
    "in_x": FieldInfo("入切线 X", "关键帧入切线。"),
    "in_y": FieldInfo("入切线 Y", "关键帧入切线。"),
    "out_x": FieldInfo("出切线 X", "关键帧出切线。"),
    "out_y": FieldInfo("出切线 Y", "关键帧出切线。"),
    "pre": FieldInfo("前置外推", "曲线起点前的外推方式。", (0, 4), integer=True),
    "post": FieldInfo("后置外推", "曲线终点后的外推方式。", (0, 4), integer=True),
    "rot_order": FieldInfo("旋转顺序", "欧拉角旋转顺序编号。", (0, 5), integer=True),
    "stype": FieldInfo("子类型", "子类型编号。", (0, 10), integer=True),
    "joint": FieldInfo("关节", "关节骨骼名。"),
}

SECTION_INFO_EN: dict[str, SectionInfo] = {
    "Bounding": SectionInfo("Bounds", "Overall model bounds used for camera clipping and occlusion calculations."),
    "Collider": SectionInfo("Collider", "Collision shapes used for scene or character interaction."),
    "SpecificCollider": SectionInfo("Specific Collider", "Named colliders referenced by dynamic-bone specific collider lists."),
    "DynamicBone": SectionInfo("Dynamic Bones (Physics)", "Secondary motion for hair, clothing, chest, and accessories."),
    "DynamicBoneCollider": SectionInfo("Dynamic Bone Colliders", "Colliders that keep dynamic bones from clipping through the model."),
    "NeighborBones": SectionInfo("Neighbor Bones", "Constraints linking adjacent dynamic-bone chains."),
    "LookIK": SectionInfo("Look IK", "Automatic head/spine rotation when looking at a target."),
    "TwoBoneIK": SectionInfo("Two-Bone IK", "Two-segment IK for arms or legs."),
    "Locators": SectionInfo("Locators", "Attachment points for effects, weapons, props, and accessories."),
    "Lights": SectionInfo("Lights", "Model-owned light definitions."),
    "LOD": SectionInfo("LOD", "Level-of-detail switching settings."),
    "Occluder": SectionInfo("Occluder", "Whether this model participates in occlusion culling."),
    "Extra": SectionInfo("Extra", "Miscellaneous parameters."),
    "Animation": SectionInfo("Animation", "Animation-related settings."),
    "DrivenKeys": SectionInfo("Driven Keys", "Keyframe curves driven by another property."),
    "Drivers": SectionInfo("Drivers", "Inputs for driven keyframes."),
    "Keys": SectionInfo("Keys", "Keyframe points on a driven curve."),
    "TwoBoneIk": SectionInfo("Two-Bone IK", "Two-segment IK for arms or legs."),
}

FIELD_LABELS_EN: dict[str, str] = {
    "damping": "Damping",
    "damping_min": "Min Damping",
    "damping_max": "Max Damping",
    "damping_velocity_ratio": "Velocity Damping Ratio",
    "is_dynamic_damping": "Dynamic Damping",
    "gravity": "Gravity",
    "resilience": "Resilience",
    "rotation_limit": "Rotation Limit",
    "stretch_limit": "Stretch Limit",
    "stretch_resilience": "Stretch Resilience",
    "is_enable_stretch": "Allow Stretch",
    "wind_influence": "Wind Influence",
    "collision_radius": "Collision Radius",
    "freeze_axis": "Freeze Axis",
    "driven_infl": "Driven Influence",
    "is_disable": "Disabled",
    "ignore_collision": "Ignore Collision",
    "node": "Bone Node",
    "name": "Name",
    "type": "Type",
    "need_specific": "Specific Only",
    "param0": "Parameter 0",
    "param1": "Parameter 1",
    "param2": "Parameter 2",
    "param3": "Parameter 3",
    "offset_x": "Offset X",
    "offset_y": "Offset Y",
    "offset_z": "Offset Z",
    "offset_rot_x": "Rotation Offset X",
    "offset_rot_y": "Rotation Offset Y",
    "offset_rot_z": "Rotation Offset Z",
    "off_x": "Position X",
    "off_y": "Position Y",
    "off_z": "Position Z",
    "rot_x": "Rotation X",
    "rot_y": "Rotation Y",
    "rot_z": "Rotation Z",
    "look_offset_x": "Look Offset X",
    "look_offset_y": "Look Offset Y",
    "look_offset_z": "Look Offset Z",
    "up_vec_x": "Up Vector X",
    "up_vec_y": "Up Vector Y",
    "up_vec_z": "Up Vector Z",
    "rx_limit_max": "X Rotation Max",
    "rx_limit_min": "X Rotation Min",
    "ry_limit_max": "Y Rotation Max",
    "ry_limit_min": "Y Rotation Min",
    "axis_x": "Axis X",
    "axis_y": "Axis Y",
    "axis_z": "Axis Z",
    "root": "Root Joint",
    "middle": "Middle Joint",
    "top": "End Joint",
    "omit_middle": "Omit Middle",
    "length_limit": "Length Limit",
    "root_rot_max": "Root Rotation Max",
    "root_rot_min": "Root Rotation Min",
    "mid_rot_max": "Middle Rotation Max",
    "mid_rot_min": "Middle Rotation Min",
    "size": "Size",
    "offset": "Offset",
    "x": "X",
    "y": "Y",
    "z": "Z",
    "is_valid": "Enabled",
    "door_type": "Door Type",
    "attr": "Attribute",
    "driven": "Driven Object",
    "driven_attr": "Driven Attribute",
    "target": "Target",
    "blend": "Blend",
    "interp": "Interpolation",
    "time": "Time",
    "value": "Value",
    "in_x": "In Tangent X",
    "in_y": "In Tangent Y",
    "out_x": "Out Tangent X",
    "out_y": "Out Tangent Y",
    "pre": "Pre Extrapolation",
    "post": "Post Extrapolation",
    "rot_order": "Rotation Order",
    "stype": "Subtype",
    "joint": "Joint",
}

FIELD_HELPS_EN: dict[str, str] = {
    "damping": "Higher values damp motion faster and make the chain steadier.",
    "damping_min": "Lower damping limit used when dynamic damping is enabled.",
    "damping_max": "Upper damping limit used when dynamic damping is enabled.",
    "damping_velocity_ratio": "How strongly velocity drives the dynamic damping blend.",
    "is_dynamic_damping": "When enabled, damping changes between the minimum and maximum values based on motion speed.",
    "gravity": "Negative values pull downward; 0 disables gravity influence.",
    "resilience": "Force used to return the bone to its original pose.",
    "rotation_limit": "Maximum allowed swing angle in radians.",
    "stretch_limit": "Maximum stretch ratio; 0 disables stretch.",
    "stretch_resilience": "Force used to restore the original bone length after stretching.",
    "is_enable_stretch": "Whether this bone is allowed to stretch.",
    "wind_influence": "Multiplier for scene wind influence.",
    "collision_radius": "Sphere radius used for collision; 0 disables collision for this joint.",
    "freeze_axis": "Axis constraint mode; values usually map to none or X/Y/Z planes.",
    "driven_infl": "Weight of animation-driver influence on this item.",
    "is_disable": "Disables physics simulation for this bone item.",
    "ignore_collision": "Makes this dynamic-bone chain ignore colliders.",
    "node": "Bound skeleton bone name.",
    "name": "Identifier name for this entry.",
    "type": "Shape or behavior type number.",
    "need_specific": "Restricts this collider to explicit SpecificCollider references.",
    "param0": "Primary shape parameter, often radius depending on collider type.",
    "param1": "Secondary shape parameter, often capsule length or height.",
    "param2": "Additional shape parameter whose meaning depends on collider type.",
    "param3": "Additional shape parameter whose meaning depends on collider type.",
    "offset_x": "Position offset relative to the bound bone.",
    "offset_y": "Position offset relative to the bound bone.",
    "offset_z": "Position offset relative to the bound bone.",
    "offset_rot_x": "Rotation offset relative to the bound bone, in radians.",
    "offset_rot_y": "Rotation offset relative to the bound bone, in radians.",
    "offset_rot_z": "Rotation offset relative to the bound bone, in radians.",
    "rot_x": "Rotation angle in radians.",
    "rot_y": "Rotation angle in radians.",
    "rot_z": "Rotation angle in radians.",
    "off_x": "Position offset relative to the reference point.",
    "off_y": "Position offset relative to the reference point.",
    "off_z": "Position offset relative to the reference point.",
    "look_offset_x": "X offset of the look-at target point.",
    "look_offset_y": "Y offset of the look-at target point.",
    "look_offset_z": "Z offset of the look-at target point.",
    "up_vec_x": "X component of the up vector used by IK solving.",
    "up_vec_y": "Y component of the up vector used by IK solving.",
    "up_vec_z": "Z component of the up vector used by IK solving.",
    "rx_limit_max": "Maximum allowed rotation around the X axis, in radians.",
    "rx_limit_min": "Minimum allowed rotation around the X axis, in radians.",
    "ry_limit_max": "Maximum allowed rotation around the Y axis, in radians.",
    "ry_limit_min": "Minimum allowed rotation around the Y axis, in radians.",
    "axis_x": "X component of the IK bend axis vector.",
    "axis_y": "Y component of the IK bend axis vector.",
    "axis_z": "Z component of the IK bend axis vector.",
    "root": "Root bone of the IK chain.",
    "middle": "Middle bone of the IK chain.",
    "top": "End bone of the IK chain.",
    "omit_middle": "Prevents the middle joint from rotating during solving.",
    "length_limit": "Stretch length limit ratio for the IK chain.",
    "root_rot_max": "Maximum allowed root-joint rotation, in radians.",
    "root_rot_min": "Minimum allowed root-joint rotation, in radians.",
    "mid_rot_max": "Maximum allowed middle-joint rotation, in radians.",
    "mid_rot_min": "Minimum allowed middle-joint rotation, in radians.",
    "size": "Bounds size.",
    "offset": "Bounds center offset.",
    "x": "X component.",
    "y": "Y component.",
    "z": "Z component.",
    "is_valid": "Whether this entry is enabled.",
    "door_type": "Behavior type number for door objects.",
    "attr": "Name of the driven or driver attribute.",
    "driven": "Name of the driven node or object.",
    "driven_attr": "Attribute on the driven object.",
    "target": "Target node or object name.",
    "blend": "Blend weight.",
    "interp": "Interpolation mode number.",
    "time": "Keyframe time.",
    "value": "Numeric keyframe or parameter value.",
    "in_x": "Incoming tangent X value for a keyframe.",
    "in_y": "Incoming tangent Y value for a keyframe.",
    "out_x": "Outgoing tangent X value for a keyframe.",
    "out_y": "Outgoing tangent Y value for a keyframe.",
    "pre": "Curve extrapolation mode before the first key.",
    "post": "Curve extrapolation mode after the last key.",
    "rot_order": "Euler rotation order number.",
    "stype": "Subtype number.",
    "joint": "Skeleton joint name.",
}


def _is_english(language: str | None) -> bool:
    return bool(language and language.startswith("en"))


def section_label(name: str, language: str = "zh_CN") -> str:
    if _is_english(language):
        info = SECTION_INFO_EN.get(name)
        return f"{info.label} {name}" if info else name
    info = SECTION_INFO.get(name)
    return f"{info.label} {name}" if info else name


def section_help(name: str, language: str = "zh_CN") -> str:
    if _is_english(language):
        info = SECTION_INFO_EN.get(name)
        return info.help if info else ""
    info = SECTION_INFO.get(name)
    return info.help if info else ""


def field_label(name: str, language: str = "zh_CN") -> str:
    if _is_english(language):
        label = FIELD_LABELS_EN.get(name)
        return f"{label} {name}" if label else name
    info = FIELD_INFO.get(name)
    return f"{info.label} {name}" if info else name


def field_help(name: str, language: str = "zh_CN") -> str:
    if _is_english(language):
        return FIELD_HELPS_EN.get(name, "")
    info = FIELD_INFO.get(name)
    return info.help if info else ""


def field_range(name: str, current: float) -> tuple[float, float]:
    info = FIELD_INFO.get(name)
    if info and info.range:
        low, high = info.range
        # Widen the range when the current value already exceeds it so the
        # slider never clamps an existing value.
        if current < low:
            low = current
        if current > high:
            high = current
        return float(low), float(high)
    if current == 0:
        return -1.0, 1.0
    span = abs(current) * 2
    return (-span, span) if current < 0 else (0.0, span)


def field_is_integer(name: str) -> bool:
    info = FIELD_INFO.get(name)
    return bool(info and info.integer)


# -- left/right symmetry -------------------------------------------------------

_MIRROR_TOKEN = {
    "left": "right",
    "right": "left",
    "l": "r",
    "r": "l",
}


def _swap_case_like(template: str, replacement: str) -> str:
    if template.isupper():
        return replacement.upper()
    if template[:1].isupper():
        return replacement.capitalize()
    return replacement


def mirror_name(name: str) -> str | None:
    """Return the left/right mirrored identifier, or None when not symmetric.

    Handles CamelCase Left/Right anywhere in the name (LeftBreast_Top ->
    RightBreast_Top) and single-letter L/R tokens separated by underscores
    (L_Skirt01 -> R_Skirt01).
    """
    for word in ("Left", "Right", "left", "right", "LEFT", "RIGHT"):
        if word in name:
            return name.replace(word, _swap_case_like(word, _MIRROR_TOKEN[word.lower()]))

    parts = re.split(r"(_)", name)
    changed = False
    for index, part in enumerate(parts):
        if part.lower() in ("l", "r"):
            parts[index] = _swap_case_like(part, _MIRROR_TOKEN[part.lower()])
            changed = True
    return "".join(parts) if changed else None
