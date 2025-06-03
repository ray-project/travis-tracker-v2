import React, { useContext, useState } from "react";
import { Col, Row, Typography } from "antd";
import { BugFilled } from "@ant-design/icons";
import { SiteCommitTooltip, SiteFailedTest } from "../interface";
import SegmentedBar from "./segment";
import DetailModal from "./detail";
import githubIcon from "../static/github-icon.png";

interface Prop {
  case: SiteFailedTest;
  compact: boolean;
  githubState: Map<string, any>;
}

const getRate = (
  commits: SiteCommitTooltip[],
  includeFlaky: boolean = false
) => {
  let flaky = 0, failed = 0, pass = 0;
  
  for (const c of commits) {
    if (c.num_failed === null) {
      continue;
    } else if (c.num_failed === 0 && c.num_flaky === 0) {
      pass += 1;
    } else if ((c.num_flaky || 0) > 0) {
      flaky += 1;
    } else {
      failed += 1;
    }
  }

  const totalRuns = flaky + failed + pass;
  return totalRuns === 0 ? 0 : ((failed + (includeFlaky ? flaky : 0)) / totalRuns) * 100;
}

const TestCase: React.FC<Prop> = (props) => {
  const [showModal, setShowModal] = useState(false);
  const githubUrlState = props.githubState.get(props.case.name)

  return (
    <>
      {!props.compact && (
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
          onClick={() => setShowModal(true)}
        >
          <Row>
            <Col>{props.case.name}</Col>
            {props.case.is_labeled_flaky && <Col span={2}>🥶</Col>}

            <Col flex="auto"></Col>

            {githubUrlState &&
              <Col span={2}>
                <img src={githubIcon} height={"18px"}></img>
                {" "}
                {githubUrlState.state === "open" ? "🚧" : "✅"}
              </Col>
            }

            {/* {props.case.build_time_stats && (
              // Median build time
              <Col span={2}>⏱{props.case.build_time_stats[1].toFixed(2)}s</Col>
            )} */}

            <Col span={3}>
              <div className="item failed" style={{ marginTop: "3px" }}></div>
              {getRate(props.case.status_segment_bar, false).toFixed(0)}%
            </Col>
            <Col span={3}>
              <div className="item failed" style={{ marginTop: "3px" }}></div>
              <div className="item flaky" style={{ marginTop: "3px" }}></div>
              {getRate(
                props.case.status_segment_bar,
                true
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
          owner={props.case.owner}
          visible={showModal}
          links={props.case.travis_links}
          onClose={() => setShowModal(false)}
          githubState={props.githubState}
        ></DetailModal>
      )}
    </>
  );
};

export default TestCase;
