from pydantic import BaseModel, Field, model_validator

class Delivery(BaseModel):
    distance_km: float = Field(ge=.1, le=500, allow_inf_nan=False)
    n_stops: int = Field(ge=1, le=60)
    hour: int = Field(ge=0, le=23)
    weekday: int = Field(ge=0, le=6)
    traffic_index: float = Field(ge=0, le=1, allow_inf_nan=False)
    rain: int = Field(ge=0, le=1)
    weight_kg: float = Field(gt=0, le=1000, allow_inf_nan=False)

    @model_validator(mode='after')
    def feasible(self):
        if self.distance_km > 150 and self.n_stops > 20:
            raise ValueError('infeasible delivery')
        return self

class Batch(BaseModel):
    instances: list[Delivery] = Field(min_length=1, max_length=500)

