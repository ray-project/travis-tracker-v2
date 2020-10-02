import React from "react";

interface Props {
  buildTime: number;
}

const BuildTimeFooter: React.FC<Props> = ({ buildTime }) => {
  const now = Date.now().valueOf();
  const minutePassed = (now - buildTime) / 1000 / 60;
  return (
    <div style={{ padding: "2%" }}>
      Page Generated: {minutePassed.toFixed(0)} minutes ago
    </div>
  );
};

export default BuildTimeFooter;
