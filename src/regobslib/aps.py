# To enable postponed evaluation of annotations (default for 3.10)
from __future__ import annotations

import datetime as dt

import pandas as pd
from collections import OrderedDict
from typing import Union, Type, List, Dict, Optional, cast, Iterator

from .region import SnowRegion
from .submit import Dictable
from .misc import Container, Ordered, OrderedElements

ApsJsonData = Dict[str, Union[int, float]]
ApsJsonRegion = Dict[str, Union[str, List[ApsJsonData]]]
ApsJsonDay = Dict[str, Union[str, bool, List[ApsJsonRegion]]]
ApsJsonFull = Dict[str, List[ApsJsonDay]]
ApsJson = Union[ApsJsonData,
                ApsJsonRegion,
                ApsJsonDay,
                ApsJsonFull]

ApsDict = Union[Dict[Union[str, int],
                     Optional[Union[str,
                                    int,
                                    float,
                                    'ApsDict']]],
                List['ApsDict']]


class Deserializable:
    @classmethod
    def deserialize(cls,
                    json: ApsJson,
                    data_type: Type[Data]) -> Deserializable:
        raise NotImplementedError()


class Frameable:
    def to_frame(self, elevation: int = None, level_index: int = None) -> pd.DataFrame:
        raise NotImplementedError()

    def to_csv(self, filename: str, elevation: int = None, level_index: int = None) -> Optional[str]:
        return self.to_frame(elevation, level_index).to_csv(filename, sep=";")

    @staticmethod
    def read_csv(filename: str) -> pd.DataFrame:
        raise NotImplementedError()


class Data(Dictable):
    DATA_ID: int = None

    def __init__(self):
        self.perc00 = None
        self.perc05 = None
        self.perc25 = None
        self.perc50 = None
        self.perc75 = None
        self.perc95 = None
        self.perc100 = None

    def to_dict(self) -> ApsDict:
        return {
            0: self.perc00,
            5: self.perc05,
            25: self.perc25,
            50: self.perc50,
            75: self.perc75,
            95: self.perc95,
            100: self.perc100,
        }

    def to_series(self) -> pd.Series:
        series = pd.Series(self.to_dict())
        series.index = series.index.set_names("percentile")
        series.name = WEATHER_ATTRS[type(self)]
        return series

    @classmethod
    def deserialize(cls, json: ApsJson):
        data = cls()
        data.perc00 = json["Minimum"]
        data.perc05 = json["Perc05"]
        data.perc25 = json["FirstQuartile"]
        data.perc50 = json["Median"]
        data.perc75 = json["ThirdQuartile"]
        data.perc95 = json["Perc05"]
        data.perc100 = json["Maximum"]
        return data


class Precip(Data):
    WEATHER_PARAM = 0


class PrecipMax(Data):
    WEATHER_PARAM = 100


class Temp(Data):
    WEATHER_PARAM = 17


class Wind(Data):
    WEATHER_PARAM = 18


class SnowDepth(Data):
    WEATHER_PARAM = 2002


class NewSnow(Data):
    WEATHER_PARAM = 2013


class NewSnowMax(Data):
    WEATHER_PARAM = 2113


WEATHER_ATTRS: Dict[Type[Data], str] = {
    Precip: 'precip',
    PrecipMax: 'precip_max',
    Temp: 'temp',
    Wind: 'wind',
    SnowDepth: 'snow_depth',
    NewSnow: 'new_snow',
    NewSnowMax: 'new_snow_max',
}


class Aps(Container, Deserializable, Dictable, Frameable):
    """A collection of regions with timelines of APS data

    The object is indexable and iterable.

    Structure:
    Aps -> {SnowRegion: Timeline} -> {dt.Date: Day} -> [Level] -> Data
    """
    _elems: OrderedDict[SnowRegion, Timeline]

    def to_dict(self) -> ApsDict:
        return {
            timeline.get_region(): timeline.to_dict()
            for timeline in self._sort()._filter_empty() if timeline
        }

    def to_frame(self, elevation: int = None, level_index: int = None) -> pd.DataFrame:
        df = pd.concat({
            timeline.get_region(): timeline.to_frame(elevation, level_index)
            for timeline in self._sort()._filter_empty() if timeline
        }, names=["region", "date", "elevation"])
        df.name = "aps"
        df.sort_index(inplace=True,
                      level=0,
                      kind='mergesort',
                      sort_remaining=False)
        df.index = df.index.set_levels([
            df.index.levels[0],
            pd.to_datetime(df.index.levels[1]),
            df.index.levels[2],
        ])
        return df

    @staticmethod
    def read_csv(filename: str) -> pd.DataFrame:
        df = pd.read_csv(filename, sep=";", header=[0, 1], index_col=[0, 1, 2])
        df.index = df.index.set_levels([
            df.index.levels[0],
            pd.to_datetime(df.index.levels[1]),
            df.index.levels[2],
        ])
        return df

    @staticmethod
    def parse_level(string):
        l_min, l_max = [int(level) for level in string.split("-", 1)]
        return l_min, l_max

    @classmethod
    def deserialize(cls, json: ApsJsonFull, data_type: Type[Data]) -> Aps:
        aps = cls()
        timeline = Timeline.deserialize(json, data_type)
        aps[timeline.get_region()] = timeline
        return aps

    def _sort(self) -> Aps:
        return cast(Aps, super()._sort())

    def _filter_empty(self) -> Aps:
        return cast(Aps, super()._filter_empty())

    def __getitem__(self,
                    key: Union[dt.date, SnowRegion, slice, List[dt.date], List[SnowRegion]]) -> Union[Timeline, Aps]:
        if isinstance(key, dt.date) \
                or isinstance(key, slice) and (isinstance(key.start, dt.date) or isinstance(key.stop, dt.date)) \
                or isinstance(key, list) and len(key) and isinstance(key[0], dt.date):
            aps = type(self)()
            for timeline in self:
                aps[timeline.get_region()] = timeline[key]
            return aps
        return cast(Union[Timeline, Aps], super().__getitem__(key))

    def __setitem__(self, key: SnowRegion, elem: Timeline) -> None:
        return super().__setitem__(key, elem)

    def __iter__(self) -> Iterator[Timeline]:
        return cast(Iterator[Timeline], super().__iter__())


class Timeline(Container, Deserializable, Dictable, Frameable):
    """A collection of Days with APS data

    The object is indexable and iterable.

    Structure:
    Timeline -> {dt.Date: Day} -> [Level] -> Data
    """

    def to_dict(self) -> ApsDict:
        return {
            day.date.isoformat(): day.to_dict()
            for day in self._sort()._filter_empty() if day
        }

    def to_frame(self, elevation: int = None, level_index: int = None) -> pd.DataFrame:
        """ Creates a DataFrame of the data.
        """
        # This was previously done by calling to_frame() on all contained objects
        # but was rewritten due to performance issues.
        levels = {
            (day.date, lvl.get_name()): {
                (data_type, attr_name): attr
                for data_type, data in lvl.to_dict().items() if data for attr_name, attr in data.items()}
            for day in self if day for lvl in day.levels
            if elevation is None and level_index is None
                or elevation and lvl.floor <= elevation and (not lvl.roof or elevation < lvl.roof)
                or lvl.index == level_index
        }
        df = pd.DataFrame(levels).T
        df.name = self.get_region()
        df.index = df.index.set_names(["date", "elevation"])
        df.columns = df.columns.set_names(["data_type", "attr"])
        df.sort_index(inplace=True,
                      level=0,
                      kind='mergesort',
                      sort_remaining=False)
        df.index = df.index.set_levels([
            pd.to_datetime(df.index.levels[0]),
            df.index.levels[1],
        ])
        return df

    def get_region(self) -> SnowRegion:
        if not self:
            raise ValueError("No days to find region from")
        return next(iter(self)).region

    @staticmethod
    def read_csv(filename: str) -> pd.DataFrame:
        df = pd.read_csv(filename, sep=";", header=[0, 1], index_col=[0, 1])
        df.index = df.index.set_levels([
            pd.to_datetime(df.index.levels[0]),
            df.index.levels[1],
        ])
        return df

    @classmethod
    def deserialize(cls, json: ApsJsonFull, data_type: Type[Data]) -> Timeline:
        timeline = cls()
        for day in json["TimeLine"]:
            date = dt.date.fromisoformat(day["FormattedDate"][:10])
            timeline[date] = Day.deserialize(day, data_type)
        return timeline

    def _sort(self) -> Timeline:
        return cast(Timeline, super()._sort())

    def _filter_empty(self) -> Timeline:
        return cast(Timeline, super()._filter_empty())

    def __getitem__(self, key: Union[dt.date, slice, List[dt.date]]) -> Union[Day, Timeline]:
        return cast(Union[Day, Timeline], super().__getitem__(key))

    def __setitem__(self, key: Ordered, elem: OrderedElements):
        return super().__setitem__(key, elem)

    def __iter__(self) -> Iterator[Day]:
        return cast(Iterator[Day], super().__iter__())


class Day(Deserializable, Dictable, Frameable):
    date: dt.date = None
    region: SnowRegion = None

    def __init__(self):
        """A collection of Days with APS data

        The day contains the attribute .levels, which is a list
        of Levels.
        """
        self.levels: List[Level] = []

    def to_dict(self) -> ApsDict:
        return [level.to_dict() for level in self.levels]

    def to_frame(self, elevation: int = None, level_index: int = None) -> pd.DataFrame:
        if elevation is not None and level_index is not None:
            raise ValueError("Only one of elevation and level_index parameters can be defined")
        levels = {
            lvl.get_name(): {
                (data_type, attr_name): attr
                for data_type, data in lvl.to_dict().items() if data for attr_name, attr in data.items()}
            for lvl in self.levels
            if elevation is None and level_index is None
                or elevation and lvl.floor <= elevation and (not lvl.roof or elevation < lvl.roof)
                or lvl.index == level_index
        }
        df = pd.DataFrame(levels).T
        df.index.name = "elevation"
        df.columns = df.columns.set_names(["data_type", "attr"])
        df.name = self.date.isoformat()
        df = df.loc[df.astype('bool').any(axis=1)]
        df = df.loc[df.index != '0']
        return df

    def assimilate(self, other: Day) -> Day:
        if self.date != other.date or self.region != other.region:
            raise ValueError("Incompatible days")
        day = Day()
        day.date = self.date
        day.region = self.region
        if not self.levels:
            day.levels = other.levels
        elif not other.levels:
            day.levels = self.levels
        else:
            for i in range(max(len(self.levels), len(other.levels))):
                self_i = min(i, len(self.levels) - 1)
                other_i = min(i, len(other.levels) - 1)
                level = self.levels[self_i].assimilate(other.levels[other_i])
                day.levels.append(level)
        return day

    @staticmethod
    def read_csv(filename: str) -> pd.DataFrame:
        return pd.read_csv(filename, sep=";", header=[0, 1], index_col=[0])

    @classmethod
    def deserialize(cls, json: ApsJsonDay, data_type: Type[Data]) -> Day:
        region_list = json["Regions"]
        if not region_list:
            raise ValueError("No regions in timeline")

        day = cls()
        day.date = dt.date.fromisoformat(json["FormattedDate"][:10])
        day.region = SnowRegion(int(region_list[0]["RegionId"]))

        elevation_list = region_list[0]["ElevationData"]
        if not elevation_list:
            return day

        for level in elevation_list:
            day.levels.append(Level.deserialize(level, data_type))

        return day

    def __bool__(self) -> bool:
        return any(self.levels)


class Level(Deserializable, Dictable):
    floor: int = None
    roof: int = None
    index: int = None

    def __init__(self):
        """A collection of APS data attributes.

        The data is available under the attributes:
            .precip
            .precip_max
            .temp
            .wind
            .snow_depth
            .new_snow
            .new_snow_max
        """
        for attr in WEATHER_ATTRS.values():
            setattr(self, attr, None)

    def to_dict(self) -> ApsDict:
        d = {}
        for attr in WEATHER_ATTRS.values():
            obj = getattr(self, attr)
            d[attr] = obj.to_dict() if obj else None
        return d

    def to_series(self) -> pd.Series:
        series = pd.concat({
            key: getattr(self, key).to_series()
            for key in self.to_dict().keys() if getattr(self, key)
        }, names=["data_type", "attr"])
        series.name = self.get_name()
        return series

    def get_name(self) -> str:
        return str(self.floor) + (f"-{self.roof}" if self.roof else "")

    def assimilate(self, other: Level) -> Level:
        def max_or_not_none(self_: int, other_: int):
            return max(self_, other_) if self_ and other_ else self_ or other_

        level = Level()
        level.floor = max_or_not_none(self.floor, other.floor)
        level.roof = max_or_not_none(self.roof, other.roof)
        level.index = max_or_not_none(self.index, other.index)

        for attr in WEATHER_ATTRS.values():
            s, o = getattr(self, attr), getattr(other, attr)
            if bool(s) != bool(o):
                setattr(level, attr, s or o)
            elif s and o:
                raise ValueError(f"Both levels have valid {attr} data")

        return level

    @classmethod
    def deserialize(cls, json: ApsJsonData, data_type: Type[Data]) -> Level:
        if not isinstance(data_type, type):
            raise ValueError("data_type should be a type (uninstatiated class), not an object.")
        else:
            data_instance = object.__new__(data_type)
        if type(data_instance) == Data:
            raise ValueError("data_type must be a subclase of aps.Data")
        if not isinstance(data_instance, Data):
            raise ValueError("data_type must be a subclass of aps.Data")

        level = Level()
        level.floor = json["ElevationBottom"]
        level.roof = json["ElevationTop"] if json["ElevationTop"] else None
        level.index = json["ElevationBand"]

        if data_type in WEATHER_ATTRS:
            setattr(level, WEATHER_ATTRS[data_type], data_type.deserialize(json))
        else:
            raise ValueError("Unknown data_type")
        return level

    def __bool__(self) -> bool:
        return any([getattr(self, k) for k in WEATHER_ATTRS.values()])
