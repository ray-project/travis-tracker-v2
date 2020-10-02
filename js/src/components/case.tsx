import React, { useState } from "react";
import { Col, Row } from "antd";
import { BugFilled } from "@ant-design/icons";
import { SiteFailedTest } from "../interface";
import SegmentedBar from "./segment";
import DetailModal from "./detail";

interface Prop {
  case: SiteFailedTest;
}

const TestCase: React.FC<Prop> = (props) => {
  const [showModal, setShowModal] = useState(false);
  return (
    <>
      <button
        style={{
          backgroundColor: "rgba(247,209,213,0.8)",
          margin: "8px",
          marginTop: "16px",
          padding: "8px",
          paddingLeft: "16px",
          borderRadius: "4px",
          fontSize: "1.2em",
          width: "100%",
          border: "none",
        }}
      >
        <Row>
          <Col>{props.case.name}</Col>
          <Col flex="auto"></Col>
          <Col>
            <BugFilled />
          </Col>
        </Row>
      </button>
      <SegmentedBar commits={props.case.status_segment_bar}></SegmentedBar>
      <DetailModal
        visible={showModal}
        links={props.case.travis_links}
        onClose={() => setShowModal(false)}
      ></DetailModal>
    </>
  );
};

export default TestCase;
