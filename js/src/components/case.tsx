import React, { useState } from "react";
import { Col, Row, Typography } from "antd";
import { BugFilled } from "@ant-design/icons";
import { SiteFailedTest } from "../interface";
import SegmentedBar from "./segment";
import DetailModal from "./detail";

interface Prop {
  case: SiteFailedTest;
  segmentBarColorType: string;
}

const TestCase: React.FC<Prop> = (props) => {
  const [showModal, setShowModal] = useState(false);
  return (
    <>
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
          <Col>
            <BugFilled />
          </Col>
        </Row>
      </button>
      <SegmentedBar
        commits={props.case.status_segment_bar}
        segmentBarColorType={props.segmentBarColorType}
      ></SegmentedBar>
      <DetailModal
        testName={props.case.name}
        visible={showModal}
        links={props.case.travis_links}
        onClose={() => setShowModal(false)}
      ></DetailModal>
    </>
  );
};

export default TestCase;
