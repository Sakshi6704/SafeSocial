function goDetect(){
  window.location.href = "detect.html";
}

function analyze(){
  let text = document.getElementById("text").value;
  let result = document.getElementById("result");

  if(text.trim() === ""){
    result.innerText = "Please enter text!";
    result.style.color = "yellow";
    return;
  }

  let outputs = ["Hate Speech", "Offensive", "Neutral"];
  let random = outputs[Math.floor(Math.random()*3)];

  result.innerText = "Result: " + random;

  if(random === "Hate Speech"){
    result.style.color = "red";
  } 
  else if(random === "Offensive"){
    result.style.color = "orange";
  } 
  else {
    result.style.color = "lightgreen";
  }
}