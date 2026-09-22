from __future__ import annotations

from dataclasses import dataclass, field

from multicam.core.provisioning import CameraSensorOption


@dataclass(frozen=True, slots=True)
class RaspberryPiSensorDefinition:
    """Raspberry Pi overlay knowledge kept outside portable core code."""

    id: str
    name: str
    model: str
    overlay: str
    focus_type: str
    default_parameters: dict[str, str | bool] = field(default_factory=dict)

    def parameters_for_port(self, port_id: str) -> dict[str, str | bool]:
        parameters = dict(self.default_parameters)
        if port_id == "cam0":
            parameters["cam0"] = True
        elif port_id != "cam1":
            raise ValueError(f"Unknown Raspberry Pi camera port: {port_id}")
        return parameters

    def as_option(self) -> CameraSensorOption:
        return CameraSensorOption(
            id=self.id,
            name=self.name,
            model=self.model,
            focus_type=self.focus_type,
            metadata={"overlay": self.overlay},
        )


SENSOR_DEFINITIONS = (
    RaspberryPiSensorDefinition(
        id="ov5647",
        name="OV5647 (5 MP)",
        model="ov5647",
        overlay="ov5647",
        focus_type="manual",
    ),
    RaspberryPiSensorDefinition(
        id="imx219",
        name="IMX219 (8 MP)",
        model="imx219",
        overlay="imx219",
        focus_type="manual",
    ),
    RaspberryPiSensorDefinition(
        id="imx519_manual",
        name="IMX519 / B0449 (manual focus)",
        model="imx519",
        overlay="imx519",
        focus_type="manual",
        default_parameters={"vcm": "off"},
    ),
    RaspberryPiSensorDefinition(
        id="imx519_af",
        name="IMX519 (autofocus)",
        model="imx519",
        overlay="imx519",
        focus_type="autofocus",
    ),
    RaspberryPiSensorDefinition(
        id="ov64a40",
        name="OV64A40 / Arducam 64 MP",
        model="ov64a40",
        overlay="ov64a40",
        focus_type="autofocus",
    ),
)

SENSOR_BY_ID = {sensor.id: sensor for sensor in SENSOR_DEFINITIONS}
CAMERA_OVERLAY_NAMES = {sensor.overlay for sensor in SENSOR_DEFINITIONS}
