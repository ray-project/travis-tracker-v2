import React from "react";
import { Statistic, Row, Col } from "antd";
import { SiteStatItem } from "../interface";

interface Prop {
  stats: Array<SiteStatItem>;
}

const StatsPane: React.FC<Prop> = ({ stats }) => (
  <div style={{ paddingTop: "32px" }}>
    <Row justify="space-around">
      {stats.map((s) => (
        <Col key={s.key}>
          <Statistic
            title={s.key}
            value={s.value.toFixed(0)}
            valueStyle={{
              color: s.value >= s.desired_value ? "green" : "red",
              textAlign: "right",
            }}
            suffix={s.unit}
          ></Statistic>
        </Col>
      ))}
    </Row>
  </div>
);

export default StatsPane;
