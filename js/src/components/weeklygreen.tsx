import React from "react";
import { Col, Row, Tooltip } from "antd";
import { SiteWeeklyGreenMetric } from "../interface";
import "./segment.css";

interface Prop {
  data: Array<SiteWeeklyGreenMetric>;
}

const WeeklyGreenMetric: React.FC<Prop> = ({ data }) => {
  return (
    <>
      <button
          style={{
            backgroundColor: "rgba(220,220,220,0.3)",
            margin: "8px",
            marginTop: "16px",
            padding: "8px",
            paddingLeft: "16px",
            borderRadius: "4px",
            fontSize: "1.2em",
            textAlign: "left",
            width: "100%",
            border: "none",
            cursor: "pointer",
          }}
      >
        <Row><Col>{"Daily green metric"}</Col></Row>
      </button>
      <div style={{ display: "flex", width: "90%", margin: "0 auto" }}>
        {data.map((c) => {
          let className = "item";
          if (c.num_of_blockers > 0) {
            className = `item failed`;
          }

          return (
            <Tooltip key={c.date} title={<p>{c.date}</p>}>
              <div className={className} />
            </Tooltip>
          );
        })}
      </div>
    </>
  );
};

export default WeeklyGreenMetric;
