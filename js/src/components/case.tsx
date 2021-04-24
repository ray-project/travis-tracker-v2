import React, { useState } from "react";
import { Col, Row, Typography } from "antd";
import { BugFilled } from "@ant-design/icons";
import { SiteCommitTooltip, SiteFailedTest } from "../interface";
import SegmentedBar from "./segment";
import DetailModal from "./detail";

interface Prop {
  case: SiteFailedTest;
  compact: boolean;
}

const getRate = (
  testCase: SiteFailedTest,
  mapFunc: (SiteCommitTooltip) => number
) => {
  const totalFailed: number = testCase.status_segment_bar
    .map(mapFunc)
    .reduce((a, b) => a + b);
  return totalFailed;
};

const TestCase: React.FC<Prop> = (props) => {
  const [showModal, setShowModal] = useState(false);
  return (
    <>
      {!props.compact && (
        <button
          style={{
            backgroundColor: "rgba(192,192,192,0.3)",
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
          onClick={() => setShowModal(true)}
        >
          <Row>
            <Col>{props.case.name}</Col>
            <Col flex="auto"></Col>

            {props.case.is_labeled_flaky && <Col span={2}>❆</Col>}

            {props.case.build_time_stats && (
              // Median build time
              <Col span={3}>⏱{props.case.build_time_stats[1].toFixed(2)}s</Col>
            )}

            <Col span={3}>
              <div className="item failed" style={{ marginTop: "3px" }}></div>
              {getRate(props.case, (t) => t.num_failed || 0).toFixed(0)}%
            </Col>
            <Col span={3}>
              <div className="item failed" style={{ marginTop: "3px" }}></div>
              <div className="item flaky" style={{ marginTop: "3px" }}></div>
              {getRate(
                props.case,
                (t) => (t.num_flaky || 0) + (t.num_failed || 0)
              ).toFixed(0)}
              %
            </Col>

            <Col>
              <BugFilled />
            </Col>
          </Row>
        </button>
      )}

      <SegmentedBar
        commits={props.case.status_segment_bar}
        prefix={props.compact ? `||${props.case.name}||` : ""}
      ></SegmentedBar>

      {!props.compact && (
        <DetailModal
          testName={props.case.name}
          visible={showModal}
          links={props.case.travis_links}
          onClose={() => setShowModal(false)}
        ></DetailModal>
      )}
    </>
  );
};

export default TestCase;
